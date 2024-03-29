﻿#-------------------------------------------------------------------------
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
#--------------------------------------------------------------------------
from dateutil import parser
from engine.azure.storage._error import AzureException
try:
    from xml.etree import cElementTree as ETree
except ImportError:
    from xml.etree import ElementTree as ETree
from .._common_conversion import (
    _decode_base64_to_text,
    _to_str,
)
from .._deserialization import (
    _parse_properties,
    _int_to_str,
    _parse_metadata,
    _convert_xml_to_signed_identifiers,
    _bool,
)
from .models import (
    Container,
    Blob,
    BlobBlock,
    BlobBlockList,
    BlobBlockState,
    BlobProperties,
    PageRange,
    ContainerProperties,
    AppendBlockProperties,
    PageBlobProperties,
    ResourceProperties,
    BlobPrefix,
)
from ._encryption import _decrypt_blob
from ..models import _list
from .._error import(
    _validate_content_match,
    _ERROR_DECRYPTION_FAILURE,
)
from .._common_conversion import _get_content_md5

def _parse_base_properties(response):
    '''
    Extracts basic response headers.
    '''   
    resource_properties = ResourceProperties()
    resource_properties.last_modified = parser.parse(response.headers.get('last-modified'))
    resource_properties.etag = response.headers.get('etag')

    return resource_properties

def _parse_page_properties(response):
    '''
    Extracts page response headers.
    '''   
    put_page = PageBlobProperties()
    put_page.last_modified = parser.parse(response.headers.get('last-modified'))
    put_page.etag = response.headers.get('etag')
    put_page.sequence_number = _int_to_str(response.headers.get('x-ms-blob-sequence-number'))

    return put_page

def _parse_append_block(response):
    '''
    Extracts append block response headers.
    '''   
    append_block = AppendBlockProperties()
    append_block.last_modified = parser.parse(response.headers.get('last-modified'))
    append_block.etag = response.headers.get('etag')
    append_block.append_offset = _int_to_str(response.headers.get('x-ms-blob-append-offset'))
    append_block.committed_block_count = _int_to_str(response.headers.get('x-ms-blob-committed-block-count'))

    return append_block

def _parse_snapshot_blob(response, name):
    '''
    Extracts snapshot return header.
    '''   
    snapshot = response.headers.get('x-ms-snapshot')

    return _parse_blob(response, name, snapshot)

def _parse_lease(response):
    '''
    Extracts lease time and ID return headers.
    '''
    lease = {}
    lease['time'] = response.headers.get('x-ms-lease-time')
    if lease['time']:
        lease['time'] = _int_to_str(lease['time'])

    lease['id'] = response.headers.get('x-ms-lease-id')

    return lease

def _parse_blob(response, name, snapshot, validate_content=False, require_encryption=False,
                key_encryption_key=None, key_resolver_function=None, start_offset=None, end_offset=None):
    if response is None:
        return None

    metadata = _parse_metadata(response)
    props = _parse_properties(response, BlobProperties)

    # For range gets, only look at 'x-ms-blob-content-md5' for overall MD5
    content_settings = getattr(props, 'content_settings')
    if 'content-range' in response.headers:
        if 'x-ms-blob-content-md5' in response.headers:
            setattr(content_settings, 'content_md5', _to_str(response.headers['x-ms-blob-content-md5']))
        else:
            delattr(content_settings, 'content_md5')

    if validate_content:
        computed_md5 = _get_content_md5(response.body)
        _validate_content_match(response.headers['content-md5'], computed_md5)

    if key_encryption_key is not None or key_resolver_function is not None:
            try:
                response.body = _decrypt_blob(require_encryption, key_encryption_key, key_resolver_function,
                                              response, start_offset, end_offset)
            except:
                raise AzureException(_ERROR_DECRYPTION_FAILURE)

    return Blob(name, snapshot, response.body, props, metadata)

def _parse_container(response, name):
    if response is None:
        return None

    metadata = _parse_metadata(response)
    props = _parse_properties(response, ContainerProperties)
    return Container(name, props, metadata)

def _convert_xml_to_signed_identifiers_and_access(response):
    acl = _convert_xml_to_signed_identifiers(response)
    acl.public_access = response.headers.get('x-ms-blob-public-access')

    return acl

def _convert_xml_to_containers(response):
    '''
    <?xml version="1.0" encoding="utf-8"?>
    <EnumerationResults ServiceEndpoint="https://myaccount.blob.core.windows.net">
      <Prefix>string-value</Prefix>
      <Marker>string-value</Marker>
      <MaxResults>int-value</MaxResults>
      <Containers>
        <Container>
          <Name>container-name</Name>
          <Properties>
            <Last-Modified>date/time-value</Last-Modified>
            <Etag>etag</Etag>
            <LeaseStatus>locked | unlocked</LeaseStatus>
            <LeaseState>available | leased | expired | breaking | broken</LeaseState>
            <LeaseDuration>infinite | fixed</LeaseDuration>
            <PublicAccess>blob | container</PublicAccess>
          </Properties>
          <Metadata>
            <metadata-name>value</metadata-name>
          </Metadata>
        </Container>
      </Containers>
      <NextMarker>marker-value</NextMarker>
    </EnumerationResults>
    '''
    if response is None or response.body is None:
        return None

    containers = _list()
    list_element = ETree.fromstring(response.body)
    
    # Set next marker
    setattr(containers, 'next_marker', list_element.findtext('NextMarker'))

    containers_element = list_element.find('Containers')

    for container_element in containers_element.findall('Container'):
        # Name element
        container = Container()
        container.name = container_element.findtext('Name')

        # Metadata
        metadata_root_element = container_element.find('Metadata')
        if metadata_root_element is not None:
            container.metadata = dict()
            for metadata_element in metadata_root_element:
                container.metadata[metadata_element.tag] = metadata_element.text

        # Properties
        properties_element = container_element.find('Properties')
        container.properties.etag = properties_element.findtext('Etag')
        container.properties.last_modified = parser.parse(properties_element.findtext('Last-Modified'))
        container.properties.lease_status = properties_element.findtext('LeaseStatus')
        container.properties.lease_state = properties_element.findtext('LeaseState')
        container.properties.lease_duration = properties_element.findtext('LeaseDuration')
        container.properties.public_access = properties_element.findtext('PublicAccess')
        
        # Add container to list
        containers.append(container)

    return containers

LIST_BLOBS_ATTRIBUTE_MAP = {
    'Last-Modified': (None, 'last_modified', parser.parse),
    'Etag': (None, 'etag', _to_str),
    'x-ms-blob-sequence-number': (None, 'sequence_number', _int_to_str),
    'BlobType': (None, 'blob_type', _to_str),
    'Content-Length': (None, 'content_length', _int_to_str),
    'ServerEncrypted': (None, 'server_encrypted', _bool),
    'Content-Type': ('content_settings', 'content_type', _to_str),
    'Content-Encoding': ('content_settings', 'content_encoding', _to_str),
    'Content-Disposition': ('content_settings', 'content_disposition', _to_str),
    'Content-Language': ('content_settings', 'content_language', _to_str),
    'Content-MD5': ('content_settings', 'content_md5', _to_str),
    'Cache-Control': ('content_settings', 'cache_control', _to_str),
    'LeaseStatus': ('lease', 'status', _to_str),
    'LeaseState': ('lease', 'state', _to_str),
    'LeaseDuration': ('lease', 'duration', _to_str),
    'CopyId': ('copy', 'id', _to_str),
    'CopySource': ('copy', 'source', _to_str),
    'CopyStatus': ('copy', 'status', _to_str),
    'CopyProgress': ('copy', 'progress', _to_str),
    'CopyCompletionTime': ('copy', 'completion_time', _to_str),
    'CopyStatusDescription': ('copy', 'status_description', _to_str),
    'AccessTier': (None, 'blob_tier', _to_str),
    'ArchiveStatus': (None, 'rehydration_status', _to_str)
}

def _convert_xml_to_blob_list(response):
    '''
    <?xml version="1.0" encoding="utf-8"?>
    <EnumerationResults ServiceEndpoint="http://myaccount.blob.core.windows.net/" ContainerName="mycontainer">
      <Prefix>string-value</Prefix>
      <Marker>string-value</Marker>
      <MaxResults>int-value</MaxResults>
      <Delimiter>string-value</Delimiter>
      <Blobs>
        <Blob>
          <Name>blob-name</name>
          <Snapshot>date-time-value</Snapshot>
          <Properties>
            <Last-Modified>date-time-value</Last-Modified>
            <Etag>etag</Etag>
            <Content-Length>size-in-bytes</Content-Length>
            <Content-Type>blob-content-type</Content-Type>
            <Content-Encoding />
            <Content-Language />
            <Content-MD5 />
            <Cache-Control />
            <x-ms-blob-sequence-number>sequence-number</x-ms-blob-sequence-number>
            <BlobType>BlockBlob|PageBlob|AppendBlob</BlobType>
            <LeaseStatus>locked|unlocked</LeaseStatus>
            <LeaseState>available | leased | expired | breaking | broken</LeaseState>
            <LeaseDuration>infinite | fixed</LeaseDuration>
            <CopyId>id</CopyId>
            <CopyStatus>pending | success | aborted | failed </CopyStatus>
            <CopySource>source url</CopySource>
            <CopyProgress>bytes copied/bytes total</CopyProgress>
            <CopyCompletionTime>datetime</CopyCompletionTime>
            <CopyStatusDescription>error string</CopyStatusDescription>
            <AccessTier>P4 | P6 | P10 | P20 | P30 | P40 | P50 | P60 | Archive | Cool | Hot</AccessTier>
          </Properties>
          <Metadata>   
            <Name>value</Name>
          </Metadata>
        </Blob>
        <BlobPrefix>
          <Name>blob-prefix</Name>
        </BlobPrefix>
      </Blobs>
      <NextMarker />
    </EnumerationResults>
    '''
    if response is None or response.body is None:
        return None

    blob_list = _list()    
    list_element = ETree.fromstring(response.body)

    setattr(blob_list, 'next_marker', list_element.findtext('NextMarker'))

    blobs_element = list_element.find('Blobs')
    blob_prefix_elements = blobs_element.findall('BlobPrefix')
    if blob_prefix_elements is not None:
        for blob_prefix_element in blob_prefix_elements:
            prefix = BlobPrefix()
            prefix.name = blob_prefix_element.findtext('Name')
            blob_list.append(prefix)

    for blob_element in blobs_element.findall('Blob'):
        blob = Blob()
        blob.name = blob_element.findtext('Name')
        blob.snapshot = blob_element.findtext('Snapshot')

        # Properties
        properties_element = blob_element.find('Properties')
        if properties_element is not None:
            for property_element in properties_element:
                info = LIST_BLOBS_ATTRIBUTE_MAP.get(property_element.tag)
                if info is None:
                    setattr(blob.properties, property_element.tag, _to_str(property_element.text))                   
                elif info[0] is None:
                    setattr(blob.properties, info[1], info[2](property_element.text))
                else:
                    attr = getattr(blob.properties, info[0])
                    setattr(attr, info[1], info[2](property_element.text))

        # Metadata
        metadata_root_element = blob_element.find('Metadata')
        if metadata_root_element is not None:
            blob.metadata = dict()
            for metadata_element in metadata_root_element:
                blob.metadata[metadata_element.tag] = metadata_element.text
        
        # Add blob to list
        blob_list.append(blob)

    return blob_list

def _convert_xml_to_block_list(response):
    '''
    <?xml version="1.0" encoding="utf-8"?>
    <BlockList>
      <CommittedBlocks>
         <Block>
            <Name>base64-encoded-block-id</Name>
            <Size>size-in-bytes</Size>
         </Block>
      </CommittedBlocks>
      <UncommittedBlocks>
        <Block>
          <Name>base64-encoded-block-id</Name>
          <Size>size-in-bytes</Size>
        </Block>
      </UncommittedBlocks>
     </BlockList>

    Converts xml response to block list class.
    '''
    if response is None or response.body is None:
        return None

    block_list = BlobBlockList()

    list_element = ETree.fromstring(response.body)

    committed_blocks_element = list_element.find('CommittedBlocks')
    if committed_blocks_element is not None:
        for block_element in committed_blocks_element.findall('Block'):
            block_id = _decode_base64_to_text(block_element.findtext('Name', ''))
            block_size = int(block_element.findtext('Size'))
            block = BlobBlock(id=block_id, state=BlobBlockState.Committed)
            block._set_size(block_size)
            block_list.committed_blocks.append(block)

    uncommitted_blocks_element = list_element.find('UncommittedBlocks')
    if uncommitted_blocks_element is not None:
        for block_element in uncommitted_blocks_element.findall('Block'):
            block_id = _decode_base64_to_text(block_element.findtext('Name', ''))
            block_size = int(block_element.findtext('Size'))
            block = BlobBlock(id=block_id, state=BlobBlockState.Uncommitted)
            block._set_size(block_size)
            block_list.uncommitted_blocks.append(block)

    return block_list

def _convert_xml_to_page_ranges(response):
    '''
    <?xml version="1.0" encoding="utf-8"?>
    <PageList>
       <PageRange> 
          <Start>Start Byte</Start> 
          <End>End Byte</End> 
       </PageRange> 
       <ClearRange> 
          <Start>Start Byte</Start> 
          <End>End Byte</End> 
       </ClearRange> 
       <PageRange> 
          <Start>Start Byte</Start> 
          <End>End Byte</End> 
       </PageRange> 
    </PageList> 
    '''
    if response is None or response.body is None:
        return None

    page_list = list()

    list_element = ETree.fromstring(response.body)

    for page_range_element in list_element:
        if page_range_element.tag == 'PageRange':
            is_cleared = False
        elif page_range_element.tag == 'ClearRange':
            is_cleared = True
        else:
            pass # ignore any unrecognized Page Range types

        page_list.append(
            PageRange(
                int(page_range_element.findtext('Start')),
                int(page_range_element.findtext('End')),
                is_cleared
            )
        )

    return page_list