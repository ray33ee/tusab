
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.discovery import build
from google.oauth2 import credentials

import io
import pickle
import sys
import json
import uuid
import os
import sys
import time
import subprocess

import hashlib

import gzip
import base64

from error import *

# Name of file containing image metadata and file information
METADATA_FILE_NAME = ".metadata"

# Folder identifier to prevent conflicts
FOLDER_IDENTIFIER = "775334298f5807bc09b8be827286e533"

# Name of folder containing image metadata folder
METADATA_FOLDER_NAME = "exploit images (" + FOLDER_IDENTIFIER + ")"

# Name of resource lock
RESOURCE_LOCK_NAME = ".mutex-"

# Name of config file
CONFIG_FILENAME = "config.json"

# If modifying these scopes, delete the file token.pickle.
DRIVESCOPES = ['https://www.googleapis.com/auth/drive']

# Size of the salt used for password hashing
SALT_LENGTH = 32

# Number of iterations in password hashing function
SHA_ITERATIONS = 100000

EMPTY_METADATA_FILE = {
    "prefix": "",
    "groups": {}
}

# IDs for metadata file and containing folder
metadataID = None
metaFolderID = None
mutexFileID = None


# Config file stored on host (not in drive)
config = None

# Runs a process using subprocess.run, with stdout redirected to stderr and raises exception if the command fails.
def runProcess(exception, text, *args):

    ret = subprocess.run(args, capture_output=True, text=text)

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

    global metaFolderID, metadataID, mutexFileID

    # get list of folders that are named METADATA_FOLDER_NAME, in the root directory and not deleted
    metaFolders = drive.files().list(q="name='" + METADATA_FOLDER_NAME + "' and not trashed",
                                     fields='files(id)').execute()["files"]

    # If none exist throw error
    if metaFolders.__len__() == 0:
        raise MetadataFolderNotFoundError("Metadata and image folder not found. Aborting...")

    # If more than one exist, throw MultipleFoldersFoundError exception
    if metaFolders.__len__() > 1:
        raise MultipleFoldersFoundError("More than one valid folder was detected.", metaFolders)

    # Get ID of folder
    folderID = metaFolders[0]['id']

    # Next get list of all files named METADATA_FILE_NAME
    metaFiles = drive.files().list(q="name='" + METADATA_FILE_NAME + "' and not trashed and '"
                                   + folderID + "' in parents",
                                   fields='files(id)').execute()["files"]

    # If this is empty, set the folder ID only
    if metaFiles.__len__() == 0:
        metaFolderID = metaFolders[0]['id']
        metadataID = None
    elif metaFiles.__len__() > 1:
        raise MultipleMetadataFilesFoundError("Multiple metadata files found.", metaFiles)
    else:
        metadataID = metaFiles[0]['id']
        metaFolderID = metaFolders[0]['id']

    # Next get a list of possible mutex files
    mutexList = drive.files().list(q="name='" + RESOURCE_LOCK_NAME + "l' and not trashed and '"
                                   + folderID + "' in parents",
                                   fields='files(id)').execute()["files"]

    mutexList += drive.files().list(q="name='" + RESOURCE_LOCK_NAME + "u' and not trashed and '"
                                    + folderID + "' in parents",
                                    fields='files(id)').execute()["files"]

    # If this is empty, return null mutex id
    if mutexList.__len__() == 0:
        mutexFileID = None
    elif mutexList.__len__() > 1:
        raise MultipleMutexFilesFoundError("Multiple mutex files found.", mutexList)
    else:
        mutexFileID = mutexList[0]['id']


def isLocked(drive):
    mutexName = drive.files().get(fileId=mutexFileID, fields='name').execute()["name"]
    return mutexName == RESOURCE_LOCK_NAME + "l"


def wait(drive):
    sys.stderr.write("Waiting for resource")
    if isLocked(drive):
        delay = 1
        while isLocked(drive):
            sys.stderr.write(".")
            time.sleep(delay)
            delay *= 1.5
    debugPrint("\nResource free.")


def lock(drive):
    bod = {
        "name": RESOURCE_LOCK_NAME + "l"
    }

    drive.files().update(body=bod, fileId=mutexFileID).execute()

    debugPrint("Metafile locked")


def unlock(drive):
    bod = {
        "name": RESOURCE_LOCK_NAME + "u"
    }

    drive.files().update(body=bod, fileId=mutexFileID).execute()

    debugPrint("Metafile unlocked")


def loadMetadata(drive):

    # By this point in the program, metadataID should be loaded with the metadata file id, but just in case we test
    if not metadataID:
        raise MetadataFileNotLoadedError("Metadata file was not loaded. "
                                         "(Are you sure that exploitStartup has been called?")

    # Download data
    request = drive.files().export_media(fileId=metadataID, mimeType='text/plain')
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
    fh = io.BytesIO(json.dumps(data).encode('utf-8'))

    # Create media body for request
    media = MediaIoBaseUpload(fh,
                              mimetype='application/vnd.google-apps.document',
                              resumable=True)

    # Call update to... update
    drive.files().update(fileId=metadataID, media_body=media).execute()


#    create empty default METADATA_FILE_NAME in Exploit folder in drive and get its ID
def createMetadata(drive):

    global metadataID

    # Setup file name and parent folder for drive
    file_info = {
        'name': METADATA_FILE_NAME,
        'mimeType': 'application/vnd.google-apps.document',
        'parents': [metaFolderID]
    }

    # Add filename prefix to metadata file
    EMPTY_METADATA_FILE["prefix"] = uuid.uuid4().hex[0:10]

    # Convert data from python dictionary to string json byte stream
    fh = io.BytesIO(json.dumps(EMPTY_METADATA_FILE).encode('utf-8'))

    # Create media body for request
    media = MediaIoBaseUpload(fh, mimetype='text/plain',
                            resumable=True)

    # Send create request and get ID of resultant file
    metadataID = drive.files().create(body=file_info, media_body=media, fields='id').execute().get('id')


def createMutex(drive):
    global mutexFileID

    # Setup file name and parent folder for drive
    file_info = {
        'name': RESOURCE_LOCK_NAME + "u",
        'mimeType': 'application/vnd.google-apps.document',
        'parents': [metaFolderID]
    }

    # Send create request and get ID of resultant file
    mutexFileID = drive.files().create(body=file_info, fields='id').execute().get('id')


def getFolders(path):

    folderName = os.path.basename(path)

    # Setup template
    folder = {
        "files": [],
        "folders": {}
    }

    # Get a list of containing files and folders
    sub = os.listdir(path)

    # recursively fetch containing stuff
    for item in sub:
        if os.path.isfile(os.path.join(path, item)):
            folder['files'].append(os.path.basename(item))
        elif os.path.isdir(os.path.join(path, item)):
            folder['folders'][item] = (getFolders(os.path.join(path, item)))

    return folder


def decodeFileStructure(message):
    # Uncomment this line to return the structure as a python object and skip the following code
    # return message

    data = base64.b64decode(message)
    return json.loads(gzip.decompress(data).decode('utf-8'))


def encodeFileStructure(file_list):
    structure = {
        "files": [],
        "folders": {}
    }

    # Iterate over file_list then recursively list containing files and folders
    for path in file_list:
        if os.path.exists(path):
            if os.path.isfile(path):
                structure['files'].append(os.path.basename(path))
            elif os.path.isdir(path):
                structure['folders'][os.path.basename(path)] = getFolders(path)

    # Uncomment this line to return the structure as a python object and skip the following code
    # return structure

    # Convert the object to json string and compress
    data = gzip.compress(json.dumps(structure).encode('utf-8'))

    base = base64.b64encode(data).decode('utf-8')

    return base, structure


# Here we feed the parent PID into an md5 generator to create an identifier unique to the parent process.
# Note: We chose not to simply use the parent PID directly as this is short enough to possibly be contained in the uuid
# string and risk accidental deletion
def getParentIdentifier():
    return hashlib.md5(str(os.getppid()).encode()).hexdigest()


# Get valid credentials for Google drive api
def getCredentials(scopes):

    global config

    if not config['user-credentials']:
        flow = InstalledAppFlow.from_client_config(client_config=config['app-credentials'], scopes=scopes)

        # Since flow.run_local_server prints a message in stdout, we redirect this to stderr
        backup = sys.stdout
        sys.stdout = sys.stderr
        creds = flow.run_local_server(port=0)
        sys.stdout = backup

        config['user-credentials'] = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "id_token": creds.id_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": scopes
        }

        with open(os.path.join(os.path.dirname(__file__), CONFIG_FILENAME), "w") as configFile:
            json.dump(config, configFile, indent=4)
    else:
        creds = credentials.Credentials(**config['user-credentials'])

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

            with open(os.path.join(os.path.dirname(__file__), CONFIG_FILENAME), "w") as configFile:
                json.dump(config, configFile, indent=4)

    return creds


def exploitStartup():

    global metadataID, metaFolderID, config

    # Load the config file - The config file, config.json should be automatically generated during installation
    with open(os.path.join(os.path.dirname(__file__), CONFIG_FILENAME), "r") as file:
        config = json.load(file)

    # Get drive service
    driveCreds = getCredentials(DRIVESCOPES)

    drive = build('drive', 'v3', credentials=driveCreds)

    # Search for METADATA_FILE_NAME
    findMetadata(drive)

    # If mutex file doesn't exist, create one
    if not mutexFileID:
        createMutex(drive)

    # If metadata file does not exist, create an empty one
    if not metadataID:
        createMetadata(drive)

    return drive, config
