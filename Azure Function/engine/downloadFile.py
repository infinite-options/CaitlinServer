# import os, uuid, sys
# from .azure.storage.blob import BlockBlobService ,PublicAccess

# def run_sample():
#     try:
#         # Create the BlockBlockService that is used to call the Blob service for the storage account
#         block_blob_service = BlockBlobService(account_name='xamarinblob', account_key='0Yaoeff3q/UxWIPoRernkxfLS+ulk2fR6YrE1CZPzx3/utu2ks6pLzXVOk/lmBh7sAhxp2enqYoIMLcRM7X+lQ==')
#         #block_blob_service = BlobServiceClient(account_name='xamarinblob', account_key='0Yaoeff3q/UxWIPoRernkxfLS+ulk2fR6YrE1CZPzx3/utu2ks6pLzXVOk/lmBh7sAhxp2enqYoIMLcRM7X+lQ==')

#         # Create a container called 'quickstartblobs'.
#         container_name ='images'
#         #block_blob_service.create_container(container_name)

#         # Set the permission so the blobs are public.
#         #block_blob_service.set_container_acl(container_name, public_access=PublicAccess.Container)

#         # Create a file in Documents to test the upload and download.
#         #local_path=os.path.abspath(os.path.curdir)

#         __location__ = os.path.realpath(
#         os.path.join(os.getcwd(), os.path.dirname(__file__)))
#         #filePath = os.path.join(__location__, 'SoundsForJay/20sec.wav')
#         local_path = os.path.join(__location__, 'SoundsForJay')
#         # List the blobs in the container
#         print("\nList blobs in the container")
#         generator = block_blob_service.list_blobs(container_name)
#         for blob in generator:
#             print("\t Blob name: " + blob.name)
#             if(".wav" in blob.name):
#                 local_file_name = blob.name

#         # Download the blob(s).
#         # Add '_DOWNLOADED' as prefix to '.txt' so you can see both files in Documents.
#         full_path_to_file2 = os.path.join(local_path, str.replace(local_file_name ,'.wav', '_DOWNLOADED.wav'))
#         print("\nDownloading blob to " + full_path_to_file2)
#         block_blob_service.get_blob_to_path(container_name, local_file_name, full_path_to_file2)

#         sys.stdout.write("Sample finished runnin3g. When you hit <any key>, the sample will be deleted and the sample "
#                          "application will exit.")
#         sys.stdout.flush()
#         input()

#         # Clean up resources. This includes the container and the temp files
#         # block_blob_service.delete_container(container_name)
#         #os.remove(full_path_to_file)
#         # os.remove(full_path_to_file2)
#     except Exception as e:
#         print(e)


# # Main method.
# if __name__ == '__main__':
#     run_sample()