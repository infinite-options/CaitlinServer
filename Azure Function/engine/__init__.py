import logging
import azure.functions as func
import os

#from .Identification.__init__ import function1
#from azure.storage import BlockBlobService, PublicAccess
#from .Identification.jay import function1
from .Identification.IdentifyFile import identify_file
from .Identification.IdentifyFile import function2
from .downloadFile import run_sample

def main(req: func.HttpRequest) -> func.HttpResponse:
    #block_blob_service = BlockBlobService(account_name='', account_key='')
    
    __location__ = os.path.realpath(
    os.path.join(os.getcwd(), os.path.dirname(__file__)))
    filePath = os.path.join(__location__, 'SoundsForJay/20sec.wav')
    
    #filepath tester
    #f = open(os.path.join(__location__, 'SoundsForJay/test.txt'))# open a text file from server

    logging.info('Python HTTP trigger function processed a request.')
    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello {name}!")
    else:
        return func.HttpResponse(
            # filepath tester. read a text file within the folder SoundsForJay, and print out the content.
            #function2(f.read()),
            run_sample(),
            #subscription key may expired.
            #identify_file('4fb1a2da4be64d0ebba737b732740a87',filePath,'true',"['(32eb9781-9d79-43bd-94e2-ee3f0828d056)','(87e616cf-5bf3-4400-ab27-ed12c4b3985d)','(a491a0cb-41d6-4334-992c-06ef70246fc1)','(fbf5086b-da62-486e-8daa-72433a3f5885)']"),
            status_code=400
        )



