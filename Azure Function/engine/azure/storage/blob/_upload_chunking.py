﻿# -------------------------------------------------------------------------
# Copyright (c) Microsoft.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# --------------------------------------------------------------------------
import sys
from threading import Lock
from time import sleep

from cryptography.hazmat.primitives.padding import PKCS7
from .._common_conversion import _encode_base64
from .._serialization import (
    url_quote,
    _get_data_bytes_only,
    _len_plus
)
from ._encryption import(
    _get_blob_encryptor_and_padder,
)
from engine.azure.common import (
    AzureHttpError,
)
from io import (BytesIO, IOBase, SEEK_CUR, SEEK_END, SEEK_SET, UnsupportedOperation)
from .models import BlobBlock
from math import ceil
from .._error import _ERROR_VALUE_SHOULD_BE_SEEKABLE_STREAM

def _upload_blob_chunks(blob_service, container_name, blob_name,
                        blob_size, block_size, stream, max_connections,
                        progress_callback, validate_content, lease_id, uploader_class, 
                        maxsize_condition=None, if_match=None, timeout=None,
                        content_encryption_key=None, initialization_vector=None, resource_properties=None):

    encryptor, padder = _get_blob_encryptor_and_padder(content_encryption_key, initialization_vector,
                                                       uploader_class is not _PageBlobChunkUploader)

    uploader = uploader_class(
        blob_service,
        container_name,
        blob_name,
        blob_size,
        block_size,
        stream,
        max_connections > 1,
        progress_callback,
        validate_content,
        lease_id,
        timeout,
        encryptor,
        padder
    )

    uploader.maxsize_condition = maxsize_condition

    # ETag matching does not work with parallelism as a ranged upload may start 
    # before the previous finishes and provides an etag
    uploader.if_match = if_match if not max_connections > 1 else None

    if progress_callback is not None:
        progress_callback(0, blob_size)

    if max_connections > 1:
        import concurrent.futures
        from threading import BoundedSemaphore

        '''
        Ensures we bound the chunking so we only buffer and submit 'max_connections' amount of work items to the executor.
        This is necessary as the executor queue will keep accepting submitted work items, which results in buffering all the blocks if
        the max_connections + 1 ensures the next chunk is already buffered and ready for when the worker thread is available.
        '''
        chunk_throttler = BoundedSemaphore(max_connections + 1)

        executor = concurrent.futures.ThreadPoolExecutor(max_connections)
        futures = []
        running_futures = []

        # Check for exceptions and fail fast.
        for chunk in uploader.get_chunk_streams():
            for f in running_futures:
                if f.done():
                    if f.exception():
                        raise f.exception()
                    else:
                        running_futures.remove(f)

            chunk_throttler.acquire()
            future = executor.submit(uploader.process_chunk, chunk)

            # Calls callback upon completion (even if the callback was added after the Future task is done).
            future.add_done_callback(lambda x: chunk_throttler.release())
            futures.append(future)
            running_futures.append(future)

        # result() will wait until completion and also raise any exceptions that may have been set.
        range_ids = [f.result() for f in futures]
    else:
        range_ids = [uploader.process_chunk(result) for result in uploader.get_chunk_streams()]

    if resource_properties:
        resource_properties.last_modified = uploader.last_modified
        resource_properties.etag = uploader.etag

    return range_ids

def _upload_blob_substream_blocks(blob_service, container_name, blob_name,
                                  blob_size, block_size, stream, max_connections,
                                  progress_callback, validate_content, lease_id, uploader_class,
                                  maxsize_condition=None, if_match=None, timeout=None):

    uploader = uploader_class(
        blob_service,
        container_name,
        blob_name,
        blob_size,
        block_size,
        stream,
        max_connections > 1,
        progress_callback,
        validate_content,
        lease_id,
        timeout,
        None,
        None
    )

    uploader.maxsize_condition = maxsize_condition

    # ETag matching does not work with parallelism as a ranged upload may start
    # before the previous finishes and provides an etag
    uploader.if_match = if_match if not max_connections > 1 else None

    if progress_callback is not None:
        progress_callback(0, blob_size)

    if max_connections > 1:
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_connections)
        range_ids = list(executor.map(uploader.process_substream_block, uploader.get_substream_blocks()))
    else:
        range_ids = [uploader.process_substream_block(result) for result in uploader.get_substream_blocks()]

    return range_ids

class _BlobChunkUploader(object):
    def __init__(self, blob_service, container_name, blob_name, blob_size,
                 chunk_size, stream, parallel, progress_callback,
                 validate_content, lease_id, timeout, encryptor, padder):
        self.blob_service = blob_service
        self.container_name = container_name
        self.blob_name = blob_name
        self.blob_size = blob_size
        self.chunk_size = chunk_size
        self.stream = stream
        self.parallel = parallel
        self.stream_start = stream.tell() if parallel else None
        self.stream_lock = Lock() if parallel else None
        self.progress_callback = progress_callback
        self.progress_total = 0
        self.progress_lock = Lock() if parallel else None
        self.validate_content = validate_content
        self.lease_id = lease_id
        self.timeout = timeout
        self.encryptor = encryptor
        self.padder = padder
        self.last_modified = None
        self.etag = None

    def get_chunk_streams(self):
        index = 0
        while True:
            data = b''
            read_size = self.chunk_size

            # Buffer until we either reach the end of the stream or get a whole chunk.
            while True:
                if self.blob_size:
                    read_size = min(self.chunk_size-len(data), self.blob_size - (index + len(data)))
                temp = self.stream.read(read_size)
                temp = _get_data_bytes_only('temp', temp)
                data += temp

                # We have read an empty string and so are at the end
                # of the buffer or we have read a full chunk.
                if temp == b'' or len(data) == self.chunk_size:
                    break

            if len(data) == self.chunk_size:
                if self.padder:
                    data = self.padder.update(data)
                if self.encryptor:
                    data = self.encryptor.update(data)
                yield index, BytesIO(data)
            else:
                if self.padder:
                    data = self.padder.update(data) + self.padder.finalize()
                if self.encryptor:
                    data = self.encryptor.update(data) + self.encryptor.finalize()
                if len(data) > 0:
                    yield index, BytesIO(data)
                break
            index += len(data)

    def process_chunk(self, chunk_data):
        chunk_bytes = chunk_data[1].read()
        chunk_offset = chunk_data[0]
        return self._upload_chunk_with_progress(chunk_offset, chunk_bytes)

    def _update_progress(self, length):
        if self.progress_callback is not None:
            if self.progress_lock is not None:
                with self.progress_lock:
                    self.progress_total += length
                    total = self.progress_total
            else:
                self.progress_total += length
                total = self.progress_total
            self.progress_callback(total, self.blob_size)

    def _upload_chunk_with_progress(self, chunk_offset, chunk_data):
        range_id = self._upload_chunk(chunk_offset, chunk_data) 
        self._update_progress(len(chunk_data))
        return range_id

    def get_substream_blocks(self):
        assert self.chunk_size is not None
        lock = self.stream_lock
        blob_length = self.blob_size

        if blob_length is None:
            blob_length = _len_plus(self.stream)
            if blob_length is None:
                raise ValueError(_ERROR_VALUE_SHOULD_BE_SEEKABLE_STREAM.format('stream'))

        blocks = int(ceil(blob_length / (self.chunk_size * 1.0)))
        last_block_size = self.chunk_size if blob_length % self.chunk_size == 0 else blob_length % self.chunk_size

        for i in range(blocks):
            yield ('BlockId{}'.format("%05d" % i),
                   _SubStream(self.stream, i * self.chunk_size, last_block_size if i == blocks - 1 else self.chunk_size,
                              lock))

    def process_substream_block(self, block_data):
        return self._upload_substream_block_with_progress(block_data[0], block_data[1])

    def _upload_substream_block_with_progress(self, block_id, block_stream):
        range_id = self._upload_substream_block(block_id, block_stream)
        self._update_progress(len(block_stream))
        return range_id

    def set_response_properties(self, resp):
        self.etag = resp.etag
        self.last_modified = resp.last_modified

class _BlockBlobChunkUploader(_BlobChunkUploader):
    def _upload_chunk(self, chunk_offset, chunk_data):
        block_id = url_quote(_encode_base64('{0:032d}'.format(chunk_offset)))
        self.blob_service._put_block(
            self.container_name,
            self.blob_name,
            chunk_data,
            block_id,
            validate_content=self.validate_content,
            lease_id=self.lease_id,
            timeout=self.timeout,
        )
        return BlobBlock(block_id)

    def _upload_substream_block(self, block_id, block_stream):
        try:
            self.blob_service._put_block(
                self.container_name,
                self.blob_name,
                block_stream,
                block_id,
                validate_content=self.validate_content,
                lease_id=self.lease_id,
                timeout=self.timeout,
            )
        finally:
            block_stream.close()
        return BlobBlock(block_id)


class _PageBlobChunkUploader(_BlobChunkUploader):
    def _upload_chunk(self, chunk_start, chunk_data):
        chunk_end = chunk_start + len(chunk_data) - 1
        resp = self.blob_service._update_page(
            self.container_name,
            self.blob_name,
            chunk_data,
            chunk_start,
            chunk_end,
            validate_content=self.validate_content,
            lease_id=self.lease_id,
            if_match=self.if_match,
            timeout=self.timeout,
        )

        if not self.parallel:
            self.if_match = resp.etag

        self.set_response_properties(resp)

class _AppendBlobChunkUploader(_BlobChunkUploader):
    def _upload_chunk(self, chunk_offset, chunk_data):
        if not hasattr(self, 'current_length'):
            resp = self.blob_service.append_block(
                self.container_name,
                self.blob_name,
                chunk_data,
                validate_content=self.validate_content,
                lease_id=self.lease_id,
                maxsize_condition=self.maxsize_condition,
                timeout=self.timeout,
            )

            self.current_length = resp.append_offset
        else:
            resp = self.blob_service.append_block(
                self.container_name,
                self.blob_name,
                chunk_data,
                validate_content=self.validate_content,
                lease_id=self.lease_id,
                maxsize_condition=self.maxsize_condition,
                appendpos_condition=self.current_length + chunk_offset,
                timeout=self.timeout,
            )

        self.set_response_properties(resp)

class _SubStream(IOBase):
    def __init__(self, wrapped_stream, stream_begin_index, length, lockObj):
        # Python 2.7: file-like objects created with open() typically support seek(), but are not
        # derivations of io.IOBase and thus do not implement seekable().
        # Python > 3.0: file-like objects created with open() are derived from io.IOBase.
        try:
            wrapped_stream.seek(0, SEEK_CUR)
        except:
            raise ValueError("Wrapped stream must support seek().")

        self._lock = lockObj
        self._wrapped_stream = wrapped_stream
        self._position = 0
        self._stream_begin_index = stream_begin_index
        self._length = length
        self._count = 0
        self._buffer = BytesIO()
        self._read_buffer_size = 4 * 1024 * 1024

    def __len__(self):
        return self._length

    def close(self):
        if self._buffer:
            self._buffer.close()
        self._wrapped_stream = None
        IOBase.close(self)

    def fileno(self):
        return self._wrapped_stream.fileno()

    def flush(self):
        pass

    def read(self, n):
        if self.closed:
            raise ValueError("Stream is closed.")

        # adjust if out of bounds
        if n + self._position >= self._length:
            n = self._length - self._position

        # return fast
        if n is 0 or self._buffer.closed:
            return b''

        # attempt first read from the read buffer
        read_buffer = self._buffer.read(n)
        bytes_read = len(read_buffer)
        bytes_remaining = n - bytes_read

        # repopulate the read buffer from the underlying stream to fulfill the request
        # ensure the seek and read operations are done atomically (only if a lock is provided)
        if bytes_remaining > 0:
            with self._buffer:
                # lock is only defined if max_connections > 1 (parallel uploads)
                if self._lock:
                    with self._lock:
                        # reposition the underlying stream to match the start of the substream
                        absolute_position = self._stream_begin_index + self._position
                        self._wrapped_stream.seek(absolute_position, SEEK_SET)
                        # If we can't seek to the right location, our read will be corrupted so fail fast.
                        if self._wrapped_stream.tell() != absolute_position:
                            raise IOError("Stream failed to seek to the desired location.")
                        buffer_from_stream = self._wrapped_stream.read(self._read_buffer_size)
                else:
                    buffer_from_stream = self._wrapped_stream.read(self._read_buffer_size)

            if buffer_from_stream:
                self._buffer = BytesIO(buffer_from_stream)
                second_read_buffer = self._buffer.read(bytes_remaining)
                bytes_read += len(second_read_buffer)
                read_buffer += second_read_buffer

        self._position += bytes_read
        return read_buffer

    def readable(self):
        return True

    def readinto(self, b):
        raise UnsupportedOperation

    def seek(self, offset, whence=0):
        if whence is SEEK_SET:
            startIndex = 0
        elif whence is SEEK_CUR:
            startIndex = self._position
        elif whence is SEEK_END:
            startIndex = self._length
            offset = - offset
        else:
            raise ValueError("Invalid argument for the 'whence' parameter.")

        pos = startIndex + offset

        if pos > self._length:
            pos = self._length
        elif pos < 0:
            pos = 0

        self._position = pos
        return pos

    def seekable(self):
        return True

    def tell(self):
        return self._position

    def write(self):
        raise UnsupportedOperation

    def writelines(self):
        raise UnsupportedOperation

    def writeable(self):
        return False