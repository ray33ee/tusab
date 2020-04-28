
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.discovery import build

import io
import pickle
import sys
import json
import uuid
import os

import subprocess

import hashlib

from error import *

# Name of file containing image metadata and file information
METADATA_FILE_NAME = ".metadata"

# Folder identifier to prevent conflicts
FOLDER_IDENTIFIER = "775334298f5807bc09b8be827286e533"

# Name of folder containing image metadata folder
METADATA_FOLDER_NAME = "exploit images metadata (" + FOLDER_IDENTIFIER + ")"

# If modifying these scopes, delete the file token.pickle.
DRIVESCOPES = ['https://www.googleapis.com/auth/drive']

EMPTY_METADATA_FILE = {
    "storage": {
        "prefix": "",
        "groups": {}
    }
}

# IDs for metadata file and containing folder
metadataID = None
metaFolderID = None


# Runs a process using subprocess.run, with stdout redirected to stderr and raises exception if the command fails.
def runProcess(exception, capture, *args):

    if capture:
        ret = subprocess.run(args, capture_output=True, text=True)
    else:
        ret = subprocess.run(args, stdout=sys.stderr, capture_output=False)

    if ret.returncode != 0:
        raise exception("" + args[0] + " failed with code " + str(ret.returncode) + ".", ret)

    return ret


# Print error messages, debug messages and informative messages on stderr
def debugPrint(message):
    sys.stderr.write("" + message + "\n")


# Print the output of commands to stdout
def outputPrint(message):
    sys.stdout.write("" + message + "\n")


# Finds metadata file in Drive and returns ID. If file does not exist, returns None
def findMetadata(drive):

    # get list of folders that are named METADATA_FOLDER_NAME, in the root directory and not deleted
    metaFolders = drive.files().list(q="name='" + METADATA_FOLDER_NAME + "' and not trashed and 'root' in parents",
                                     fields='files(id)').execute()["files"]

    debugPrint("Folders: " + str(metaFolders))

    # If none exist, return None
    if metaFolders.__len__() == 0:
        return None, None

    # If more than one exist, throw MultipleFoldersFoundError exception
    if metaFolders.__len__() > 1:
        raise MultipleFoldersFoundError("More than one valid folder was detected.", metaFolders)

    # Get ID of folder
    folderID = metaFolders[0]['id']

    # Next get list of all files named METADATA_FILE_NAME
    metaFiles = drive.files().list(q="name='" + METADATA_FILE_NAME + "' and not trashed and '"
                                       + folderID + "' in parents",
                                     fields='files(id)').execute()["files"]

    # If this is empty, throw MetadataFileNotFoundError exception
    if metaFiles.__len__() == 0:
        raise MetadataFileNotFoundError("Could not find metadata file within folder.",
                                        METADATA_FILE_NAME, METADATA_FOLDER_NAME)

    if metaFiles.__len__() > 1:
        raise MultipleMetadataFilesFoundError("Multiple metadata files found.", metaFiles)

    return metaFiles[0]['id'], metaFolders[0]['id']


def loadMetadata(drive):

    # By this point in the program, metadataID should be loaded with the metadata file id, but just in case we test
    if not metadataID:
        raise MetadataFileNotLoadedError("Metadata file was not loaded. "
                                         "(Are you sure that exploitStartup has been called?")

    # Download data
    request = drive.files().get_media(fileId=metadataID)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        debugPrint("Downloading metadata " + str(int(status.progress() * 100)) + "%")

    # Convert to json
    data = json.loads(fh.getvalue())

    return data


# Update metadata file
def saveMetadata(drive, data):

    # By this point in the program, metadataID should be loaded with the metadata file id, but just in case we test
    if not metadataID:
        raise MetadataFileNotLoadedError("Metadata file was not loaded. "
                                         "(Are you sure that exploitStartup has been called?")

    # Convert data from python dictionary to string json byte stream
    fh = io.BytesIO(bytearray(json.dumps(data, indent=4), 'utf-8'))

    # Create media body for request
    media = MediaIoBaseUpload(fh,
                              mimetype='application/json',
                              resumable=True)

    # Call update to... update
    drive.files().update(fileId=metadataID, media_body=media).execute()


#    create empty default METADATA_FILE_NAME in Exploit folder in drive and get its ID
def createMetadata(drive):

    global metadataID

    # Create folder for metadata file
    folder_info = {
        'name': METADATA_FOLDER_NAME,
        'mimeType': 'application/vnd.google-apps.folder'
    }

    # Get ID of folder
    folderID = drive.files().create(body=folder_info, fields='id').execute().get('id')

    # Setup file name and parent folder for drive
    file_info = {
        'name': METADATA_FILE_NAME,
        'parents': [folderID]
    }

    # Add filename prefix to metadata file
    EMPTY_METADATA_FILE["storage"]["prefix"] = uuid.uuid4().hex[0:10]

    # Convert data from python dictionary to string json byte stream
    fh = io.BytesIO(bytearray(json.dumps(EMPTY_METADATA_FILE, indent=4), 'utf-8'))

    # Create media body for request
    media = MediaIoBaseUpload(fh,
                            mimetype='application/json',
                            resumable=True)

    # Send create request and get ID of resultant file
    metadataID = drive.files().create(body=file_info, media_body=media, fields='id').execute().get('id')


def getFolders(path):

    # Setup template
    folder = {
        "name": os.path.basename(path),
        "files": [],
        "folders": []
    }

    # Get a list of containing files and folders
    sub = os.listdir(path)

    # recursively fetch containing stuff
    for item in sub:
        if os.path.isfile(os.path.join(path, item)):
            folder['files'].append(os.path.basename(item))
        elif os.path.isdir(os.path.join(path, item)):
            folder['folders'].append(getFolders(os.path.join(path, item)))

    return folder


def fileStructure(file_list):

    debugPrint(str(file_list))

    structure = {
        "files": [],
        "folders": []
    }

    # Iterate over file_list then recursively list containing files and folders
    for path in file_list:
        if os.path.exists(path):
            if os.path.isfile(path):
                structure['files'].append(os.path.basename(path))
            elif os.path.isdir(path):
                structure['folders'].append(getFolders(path))

    return structure


# Here we feed the parent PID into an md5 generator to create an identifier unique to the parent process.
# Note: We chose not to simply use the parent PID directly as this is short enough to possibly be contained in the uuid
# string and risk accidental deletion
def getParentIdentifier():
    return hashlib.md5(str(os.getppid()).encode()).hexdigest()


# Get valid credentials for Google drive api
def getCredentials(scopes, name):
    creds = None

    if os.path.exists(name):
        with open(name, 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', scopes)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(name, 'wb') as token:
            pickle.dump(creds, token)

    return creds

def exploitStartup():

    global metadataID, metaFolderID

    # Get drive service
    driveCreds = getCredentials(DRIVESCOPES, "drive.pickle")

    drive = build('drive', 'v3', credentials=driveCreds)

    # Search for METADATA_FILE_NAME
    metadataID, metaFolderID = findMetadata(drive)

    # If metadata file does not exist, create an empty one
    if not metadataID:
        createMetadata(drive)

    # Load the config file - The config file, config.json should be automatically generated during installation
    fp = open("./config.json", "r")
    config = json.load(fp)

    debugPrint("File ID:  " + metadataID)

    return drive, config
