import logging
#import os
import azure.functions as func
#from .Identification.IdentifyFile import identify_file

def main(queuemsg: func.QueueMessage, inputblob: func.InputStream) -> func.InputStream:
    logging.info('Python Queue trigger function processed %s', inputblob.name)
    return inputblob
    #filePath = myblob.path
    #identify_file('d0d0357f065e42b382085cebe48f042c',filePath,'true',"['(32eb9781-9d79-43bd-94e2-ee3f0828d056)','(87e616cf-5bf3-4400-ab27-ed12c4b3985d)','(a491a0cb-41d6-4334-992c-06ef70246fc1)','(fbf5086b-da62-486e-8daa-72433a3f5885)']"),
    #logging.info('Python Blob trigger function processed %s', myblob.name)
    #logging.info('filepath %s', myblob.path)