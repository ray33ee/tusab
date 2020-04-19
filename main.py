import pickle
import os
import time
import json
import uuid
import io

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.http import MediaIoBaseDownload

# Name of file containing image metadata and file information
METADATA_FILE_NAME = ".metadata"

# Name of folder containing image metadata folder
METADATA_FOLDER_NAME = "exploit images metadata"

# If modifying these scopes, delete the file token.pickle.
DRIVESCOPES = ['https://www.googleapis.com/auth/drive']

tmp_location = ".\\tmp\\"

backup_and_sync_path = "E:\\Will\\Pictures\\exploit images\\"

volume_size = 64 * 1000 * 1000 - 1000

metadataID = None
metaFolderID = None

EMPTY_METADATA_FILE = {
    "storage": {
        "prefix": "",
        "groups": {}
    }
}

# Finds metadata file and returns ID. If file does not exist, returns None
def findMetadata(drive):

    # get list of folders that are named METADATA_FOLDER_NAME, in the root directory and not deleted
    metaFolders = drive.files().list(q="name='" + METADATA_FOLDER_NAME + "' and not trashed and 'root' in parents",
                                     fields='files(id)').execute()["files"]

    print("Folders: " + str(metaFolders))

    # If none exist, return None
    if metaFolders.__len__() == 0:
        return None, None

    # If more than one exist, throw MULTIPLE_FOLDERS_FOUND exception
    if metaFolders.__len__() > 1:
        raise Exception("MULTIPLE_FOLDERS_FOUND")

    # Get ID of folder
    folderID = metaFolders[0]['id']

    # Next get list of all files named METADATA_FILE_NAME
    metaFiles = drive.files().list(q="name='" + METADATA_FILE_NAME + "' and not trashed and '"
                                       + folderID + "' in parents",
                                     fields='files(id)').execute()["files"]

    # If this is empty, throw METADATA_FILE_NOT_FOUND exception
    if metaFiles.__len__() == 0:
        raise Exception("METADATA_FILE_NOT_FOUND")

    if metaFiles.__len__() > 1:
        raise Exception("DUPLICATE_METADATA_FILES_FOUND")

    return metaFiles[0]['id'], metaFolders[0]['id']


def loadMetadata(drive):

    # By this point in the program, metadataID should be loaded with the metadata file id, but just in case we test
    if not metadataID:
        raise Exception("METADATA_FILE_NOT_LOADED")

    # Download data
    request = drive.files().get_media(fileId=metadataID)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print("Download %d%%." % int(status.progress() * 100))

    # Convert to json
    data = json.loads(fh.getvalue())

    return data


# Update metadata file
def saveMetadata(drive, data):

    # By this point in the program, metadataID should be loaded with the metadata file id, but just in case we test
    if not metadataID:
        raise Exception("METADATA_FILE_NOT_LOADED")

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

    file_info = {
        'name': METADATA_FILE_NAME,
        'parents': [folderID]
    }

    EMPTY_METADATA_FILE["storage"]["prefix"] = uuid.uuid4().hex[0:10]

    # Convert data from python dictionary to string json byte stream
    fh = io.BytesIO(bytearray(json.dumps(EMPTY_METADATA_FILE, indent=4), 'utf-8'))

    # Create media body for request
    media = MediaIoBaseUpload(fh,
                            mimetype='application/json',
                            resumable=True)

    # Send create request and get ID of resultant file
    metadataID = drive.files().create(body=file_info, media_body=media, fields='id').execute().get('id')



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


def exploitDownload(drive, file, folder):

    # Verify metadata file ID is non-null
    if not metadataID:
        raise Exception("METADATA_FILE_NOT_LOADED")

    # Read Metadata
    metadata = loadMetadata(drive)['storage']['groups']

    imageList = None

    # Search through metadata list for 'file' then extract entry
    fileList = metadata[file]['images']

    # Iterate over list of names download and convert back to archive volumes

    archiveVolumes = ""

    for entry in fileList:

        request = drive.files().get_media(fileId=entry['id'])
        fh = open(tmp_location + entry['name'], "wb")

        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print("Download %d%%." % int(status.progress() * 100))

        fh.close()

        bmpName = entry['name'][0:-3] + "bmp"

        os.system("magick convert \"" + tmp_location + entry['name'] + "\" \"" + tmp_location + bmpName + "\"")

        os.system("del \"" + tmp_location + entry['name'] + "\"")

        if os.system("tobmp \"" + tmp_location + bmpName + "\"") != 0:
            raise Exception("TOBMP_FAILED_EXCEPTION")

        archiveVolumes += "\"" + tmp_location + entry['name'][0:-4] + "\" "

    # Extract archive
    print("archive volumes " + tmp_location + fileList[0]['name'][0:-4])

    os.system("7z x " + tmp_location + fileList[0]['name'][0:-4] + " -o\"" + folder + "\"")

    # Delete archive
    os.system("del " + archiveVolumes)


def exploitStartup(drive):

    global metadataID, metaFolderID

    # Search for METADATA_FILE_NAME
    metadataID, metaFolderID = findMetadata(drive)

    if not metadataID:
        createMetadata(drive)

    print("File ID:  " + metadataID)


def exploitUpload(drive, title, file_list):

    # Download metadata
    data = loadMetadata(drive)

    # Generate file group name - name comes from the parent folder of the file group, or the file if it is individual
    titleName = title

    # Generate unique file name
    output_file_name = str(uuid.uuid4())

    # Make sure output_file_name is not already taken

    os.system("7z a -tzip -v" + str(volume_size) + " \"" + tmp_location + output_file_name + ".zip\" " + file_list)

    directory_list = os.listdir(tmp_location)

    index = 1

    while True:
        number_string = "{:03d}".format(index)
        file_part = output_file_name + ".zip." + number_string
        prefix = data['storage']['prefix']
        print(file_part)
        if directory_list.__contains__(file_part):
            os.system("tobmp \"" + tmp_location + file_part + "\"")
            os.system("magick convert -quality 0 \"" + tmp_location + output_file_name + ".zip." + number_string +
                      ".bmp\" \"" + tmp_location + output_file_name + ".zip." + number_string + ".png\"")
            os.system("del \"" + tmp_location + output_file_name + ".zip." + number_string + ".bmp\"")
            os.system("move \"" + tmp_location + output_file_name + ".zip." + number_string + ".png\" \"" +
                      backup_and_sync_path + prefix + "-" + output_file_name + ".zip." + number_string + ".png\"")
            index = index + 1
        else:
            break

    count = index - 1

    # When control flow reaches here, the input files should have been converted to images and moved to the backup
    # and sync location. Since we cannot monitor the progress of the backup and sync uploads, we must occasionally
    # probe the API for confirmation.

    delay = 1

    # If the upload has been split into volumes, the second to last volume is most likely to be the last uploaded (since
    # the last volume is probably smaller than the rest) so we monitor this one first
    search = 1 if (count == 1) else count - 1

    while True:
        imageFiles = drive.files().list(q="name='" + prefix + "-" + output_file_name + ".zip." + "{:03d}".format(search) + ".png'").execute()["files"]

        print([imageFiles, delay])
        if imageFiles.__len__() > 0:
            break
        if delay == 14:
            # Timeout
            print("Timeout")
            # quit(-3)

        time.sleep(delay)
        delay = delay + 1  # Should this need to be an arithmetic or geometric progression?

    # Verify all files are uploaded and obtain uploaded file info

    imageFileList = []

    delay = delay * 2
    while True:
        imageFileList = []

        for i in range(1, count + 1):
            imageFiles = drive.files().list(q="name='" + prefix + "-" + output_file_name + ".zip." + "{:03d}".format(i) +
                                                     ".png' and not trashed", fields="files(id,name)").execute()["files"]
            print([count, prefix + "-" + output_file_name + ".zip." + "{:03d}".format(i) + ".png", imageFiles, delay])
            if imageFiles.__len__() == 1:
                imageFileList.append(imageFiles[0])
        if imageFileList.__len__() == count:
            break
        time.sleep(delay)
        delay = delay + 1

    # Delete the files from the B&S upload directory

    for i in range(1, count + 1):
        os.system("del \"" + backup_and_sync_path + prefix + "-" + output_file_name + ".zip." + "{:03d}".format(i) + ".png\"")

    # Modify dictionary
    data["storage"]["groups"][titleName] = {
        "images": imageFileList,
        "structure": []
    }

    # Upload metadata
    saveMetadata(drive, data)


# Return list of all uploads with their corresponding file structure
def exploitList(drive):

    # Open Metadata
    data = loadMetadata(drive)

    # Get list of all file groups
    return data['storage']['groups']


# Delete entry from drive
def exploitDelete(drive, title):

    # Open metadata
    data = loadMetadata(drive)

    # Get 'title' element containing group data
    groups = data['storage']['groups'][title]['images']

    print(groups)

    # Iterate over image list deleting images
    for file in groups:
        id = file['id']
        drive.files().delete(fileId=id).execute()

    # Remove entry from metadata and save
    del data['storage']['groups'][title]

    saveMetadata(drive, data)


# Since photos are moved to Google Photos when deleted from Google drive (only if uploaded via B&S) and Google Photos
# API does not currently support deleting photos, we prefix each photo with the same 10 character string stored in the
# metadata file. This allows users to use this string to search for all images in Google Photos and manually delete.
def exploitGetPrefix(drive):
    # Get metadata
    data = loadMetadata(drive)

    # Get and return prefix
    return data['storage']['prefix'] + "-"


def test(drive):

    count = 6
    output_file_name = "clion"

    delay = 0

    while True:
        imageFileList = []

        for i in range(1, count + 1):
            imageFiles = drive.files().list(q="name='" + output_file_name + ".zip." + "{:03d}".format(i) +
                                                 ".png' and not trashed", fields="files(id,name)").execute()["files"]
            #print([count, output_file_name + ".zip." + "{:03d}".format(i) + ".png", imageFiles, delay])
            if imageFiles.__len__() == 1:
                imageFileList.append(imageFiles[0])
        if imageFileList.__len__() == count:
            print(imageFileList)
            break
        time.sleep(delay)
        delay = delay + 1



    return


def main():
    driveCreds = getCredentials(DRIVESCOPES, "drive.pickle")

    serviceDrive = build('drive', 'v3', credentials=driveCreds)

    exploitStartup(serviceDrive)

    #exploitUpload(serviceDrive, "test1", "\"E:\\Will\\Downloads\\CLion-2018.3.2.exe\"")
    #exploitDownload(serviceDrive, 'Tex and Origin', "E:\\Software Projects\\Python\\exploit_main\\files\\extract")
    exploitDelete(serviceDrive, 'Ubuntu')

    print("Prefix: " + exploitGetPrefix(serviceDrive))


if __name__ == '__main__':
    main()
