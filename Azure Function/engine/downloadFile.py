from azure.storage.blob import BlockBlobService, PublicAccess
import os, uuid, sys

def run_sample():
    try:
        # Create the BlockBlockService that is used to call the Blob service for the storage account
        block_blob_service = BlockBlobService(account_name='', account_key='')
        # Create a container called 'quickstartblobs'.
        #container_name ='quickstartblobs'
        container_name ='images'
        #block_blob_service.create_container(container_name)

        # Set the permission so the blobs are public.
        #block_blob_service.set_container_acl(container_name, public_access=PublicAccess.Container)

        # Create a file in Documents to test the upload and download.

        __location__ = os.path.realpath(
        os.path.join(os.getcwd(), os.path.dirname(__file__)))
        #local_path = os.path.join(__location__, 'SoundsForJay/')
        local_path = os.path.join(__location__)
        # not able to download file to azure function.


        #local_path=os.path.abspath(os.path.curdir)

        # List the blobs in the container
        print("\nList blobs in the container")
        generator = block_blob_service.list_blobs(container_name)
        for blob in generator:
            print("\t Blob name: " + blob.name)
            if ".wav" in blob.name:
                local_file_name = blob.name

        # Download the blob(s).
        # Add '_DOWNLOADED' as prefix to '.txt' so you can see both files in Documents.
        
        #full_path_to_file2 = os.path.join(local_path, str.replace(local_file_name ,'.txt', '_DOWNLOADED.txt'))
        full_path_to_file2 = os.path.join(local_path, str.replace(local_file_name ,'.wav', '_DOWNLOADED.wav'))
        print("\nDownloading blob to " + full_path_to_file2)
        block_blob_service.get_blob_to_path(container_name, local_file_name, full_path_to_file2)

        sys.stdout.write("Sample finished running. When you hit <any key>, the sample will be deleted and the sample "
                         "application will exit.")
        sys.stdout.flush()
        #input()
        
        # Clean up resources. This includes the container and the temp files
        #block_blob_service.delete_container(container_name)
        #os.remove(full_path_to_file)
        #os.remove(full_path_to_file2)
    except Exception as e:
        print(e)
    return "run_sample is running."


def hello():
    return "Hello World"

    # Main method.
if __name__ == '__main__':
    run_sample()