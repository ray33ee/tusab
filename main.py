import time

from algorithms import *

import shutil

from googleapiclient.http import MediaIoBaseDownload

# Volume size ensures that resultant images are no larger than 16MP.
volume_size = 64 * 1000 * 1000 - 1000


def exploitDownload(drive, title, folder, password=None):

    # Wait for lock to open
    wait(drive)

    # Close lock
    lock(drive)

    # Read Metadata
    metadata = loadMetadata(drive)['groups']

    parentidentifier = str(getParentIdentifier())

    # Check title exists
    if title not in metadata:
        raise TitleDoesNotExistError("The title '" + str(title) + "' does not exist.", title, metadata)

    # Search through metadata list for 'file' then extract entry
    fileList = metadata[title]['images']

    # Make sure a password is supplied and that the password matches the hash
    if metadata[title]['encryption']:
        if not password:
            raise PasswordRequired("Group is encrypted and requires a password. Aborting...")

        debugPrint("Validating password")

        encryption = metadata[title]['encryption']

        hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), base64.b64decode(encryption['salt']), SHA_ITERATIONS)

        if encryption['hash'] != base64.b64encode(hash).decode('utf-8'):
            raise IncorrectPassword("Incorrect Password supplied. Aborting...")

    # Make sure download files dont already exist in tmp location
    structure = decodeFileStructure(metadata[title]['structure'])

    topDirList = structure['files']
    subitems = os.listdir(folder)
    conflicts = []

    for item in structure['folders']:
        topDirList.append(item)

    for element in topDirList:
        if element in subitems:
            conflicts.append(element)

    if conflicts.__len__() != 0:
        raise OutputFilesAlreadyExist("The following files '" + str(conflicts) + "' already exist.", conflicts, folder)

    # Iterate over list of image names in group, download and convert back to archive volumes
    archiveVolumes = []

    for entry in fileList:

        request = drive.files().get_media(fileId=entry['id'])
        fh = open(os.path.join(config['temporary-file-path'], parentidentifier + "-" + entry['name']), "wb")

        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            debugPrint("Downloading " + entry['name'] + ": " + str(int(status.progress() * 100)) + "%.")

        fh.close()

        bmpName = entry['name'][0:-3] + "bmp"

        runProcess(MagickConvertFailedError, False, "magick", "convert",
                   os.path.join(config['temporary-file-path'], parentidentifier + "-" + entry['name']),
                   os.path.join(config['temporary-file-path'], parentidentifier + "-" + bmpName))

        os.remove(os.path.join(config['temporary-file-path'], parentidentifier + "-" + entry['name']))

        runProcess(b2bConvertFailedError, False, "b2b", os.path.join(config['temporary-file-path'], parentidentifier + "-" + bmpName))

        archiveVolumes.append(os.path.join(config['temporary-file-path'], parentidentifier + "-" + entry['name'][0:-4]))

    # Create password argument if needed
    if password:
        decryption = ["-p" + password]
    else:
        decryption = []

    debugPrint("Extracting archive")

    # Extract archive
    runProcess(SevenZipConvertFailedError, False, "7z", "x", *decryption,
               os.path.join(config['temporary-file-path'], parentidentifier + "-" + fileList[0]['name'][0:-4]), "-o" + folder)

    # Delete archive volumes
    for file in archiveVolumes:
        os.remove(file)

    # Unlock resource
    unlock(drive)


def exploitUpload(drive, titleName, file_list, password=None):

    # Wait for lock to open
    wait(drive)

    # Close lock
    lock(drive)

    # Download metadata
    data = loadMetadata(drive)

    # Check titlename doesnt already exist
    if titleName in data['groups']:
        raise TitleAlreadyExistsError("Title chosen is already in use.", titleName)

    # Generate unique file name
    output_file_name = str(uuid.uuid4())

    parentidentifier = getParentIdentifier()

    # Create password argument if needed
    if password:
        encryption = ["-p" + password]
    else:
        encryption = []

    debugPrint("Archiving input files and folders")

    # Add each file to archive
    runProcess(SevenZipConvertFailedError, False, "7z", "a", *encryption, "-tzip", "-v" + str(volume_size),
               os.path.join(config['temporary-file-path'], parentidentifier + "-" + output_file_name + ".zip"),
               *file_list)

    # Get list of all files and directories in tmp folder
    directory_list = os.listdir(config['temporary-file-path'])

    # Total size of input data, in bytes
    dataCount = 0

    # Iterate over all the generated archive volumes and convert to png, then move to B&S location
    index = 1
    while True:
        number_string = "{:03d}".format(index)
        file_part = parentidentifier + "-" + output_file_name + ".zip." + number_string
        prefix = data['prefix']
        if directory_list.__contains__(file_part):
            debugPrint("Processing file: " + file_part)
            res = runProcess(b2bConvertFailedError, True, "b2b",
                             os.path.join(config['temporary-file-path'], file_part))

            dataCount += json.loads(str(res.stdout))['filesize']

            runProcess(MagickConvertFailedError, False, "magick", "convert",
                       os.path.join(config['temporary-file-path'], file_part + ".bmp"),
                       os.path.join(config['temporary-file-path'], file_part + ".png"))

            os.remove(os.path.join(config['temporary-file-path'], file_part + ".bmp"))

            shutil.move(os.path.join(config['temporary-file-path'], file_part + ".png"),
                        os.path.join(config['backup-and-sync-path'], prefix + "-" + output_file_name + ".zip." + number_string + ".png"))

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

    sys.stderr.write("Waiting for uploads to complete")

    while True:
        imageFiles = drive.files().list(q="name='" + prefix + "-" + output_file_name + ".zip." + "{:03d}".format(search)
                                          + ".png'").execute()["files"]
        sys.stderr.write(".\n")
        if imageFiles.__len__() > 0:
            break
        if delay == config['timeout']:
            # Timeout
            raise UploadTimeoutError("B&S Upload timeout reached.", config['timeout'], [imageFiles, delay])

        time.sleep(delay)

        # Increasing the delay each time gives a quadratic progression, which minimises the number of API calls
        delay = delay + 1

    # At the point we can be reasonably confident that all files have been uploaded, but to make sure we
    # verify all files are uploaded and obtain uploaded file info
    imageFileList = []

    # Because we are making multiple calls per iteration, double the delays
    delay = delay * 2
    while True:
        imageFileList = []

        sys.stderr.write("...\n")
        for i in range(1, count + 1):
            imageFiles = drive.files().list(q="name='" + prefix + "-" + output_file_name + ".zip." + "{:03d}".format(i)
                                              + ".png' and not trashed", fields="files(id,name)").execute()["files"]
            if imageFiles.__len__() == 1:
                imageFileList.append(imageFiles[0])
        if imageFileList.__len__() == count:
            break
        time.sleep(delay)
        delay = delay + 1

    debugPrint("\nCleaning B&S directory")

    # Delete the files from the B&S upload directory
    for i in range(1, count + 1):
        os.remove(os.path.join(config['backup-and-sync-path'], prefix + "-" + output_file_name + ".zip." +
                  "{:03d}".format(i) + ".png"))

    debugPrint("Populating metadata entry")

    if password:
        salt = os.urandom(SALT_LENGTH)
        hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, SHA_ITERATIONS)

        encryption = {
            "salt": base64.b64encode(salt).decode('utf-8'),
            "hash": base64.b64encode(hash).decode('utf-8')
        }
    else:
        encryption = None

    text, structure = encodeFileStructure(file_list)

    outputPrint(json.dumps(structure))

    # Modify dictionary
    data["groups"][titleName] = {
        "images": imageFileList,
        "structure": text,
        "size": {
            "pixmap": None,      # Size of pixmap in bytes.
            "data": dataCount  # Total size of input data
        },
        "encryption": encryption
    }

    debugPrint("Saving metadata to Drive")

    # Upload metadata
    saveMetadata(drive, data)

    # Unlock resource
    unlock(drive)


# Return list of all uploads with their corresponding file structure
def exploitList(drive):

    # Open Metadata
    data = loadMetadata(drive)

    # Iterate over all values in groups dictionary and convert decode structures
    for key in data['groups']:
        data['groups'][key]['structure'] = decodeFileStructure(data['groups'][key]['structure'])

    # Get list of all file groups
    return data['groups']


# Delete entry from drive
def exploitRemove(drive, title):

    # Wait for lock to open
    wait(drive)

    # Close lock
    lock(drive)

    # Open metadata
    data = loadMetadata(drive)

    # Check title exists
    if not title in data['groups']:
        raise TITLE_DOES_NOT_EXIST("The title '" + title + "' does not exist.", title, data['groups'])

    # Get 'title' element containing group data
    groups = data['groups'][title]['images']

    debugPrint("Deleting images")

    # Iterate over image list deleting images
    for file in groups:
        id = file['id']
        drive.files().delete(fileId=id).execute()

    debugPrint("Removing entry from metadata file")

    # Remove entry from metadata and save
    del data['groups'][title]

    saveMetadata(drive, data)

    unlock(drive)


# Since photos are moved to Google Photos when deleted from Google drive (only if uploaded via B&S) and Google Photos
# API does not currently support deleting photos, we prefix each photo with the same 10 character string stored in the
# metadata file. This allows users to use this string to search for all images in Google Photos and manually delete.
def exploitPrefix(drive):
    # Get metadata
    data = loadMetadata(drive)

    # Get and return prefix
    return data['prefix'] + "-"


# This function will delete all files in tmp created by this processes parent
def exploitFlush():

    fileList = os.listdir(config['temporary-file-path'])

    parentIdentifier = getParentIdentifier()

    debugPrint("Removing temporary files with parent identifier " + parentIdentifier)

    for file in fileList:
        if file[0:32] == parentIdentifier:
            os.remove(os.path.join(config['temporary-file-path'], file))


# For testing purposes, not to be in final release
def deleteAll(drive):
    groups = loadMetadata(drive)['groups']

    for group in groups:
        debugPrint("Deleting group " + group)
        exploitRemove(drive, group)


def main():

    global config

    try:

        drive, config = exploitStartup()

        if sys.argv.__len__() < 2:
            debugPrint("Invalid command number of line arguments, see tusab -h. aborting...")
            sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)
        else:
            command = sys.argv[1]
            if command == "-d":
                if sys.argv.__len__() != 4 and sys.argv.__len__() != 5:
                    debugPrint("Invalid number of command line arguments for -d, see tusab -h. aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                if not os.path.exists(sys.argv[-1]):
                    debugPrint("Folder '" + sys.argv[-1] + "' does not exist. Aborting...")
                    sys.exit(INVALID_COMMAND_LINE_PATH)

                if sys.argv.__len__() == 5:
                    if sys.argv[3][0:2] == "-p":
                        exploitDownload(drive, sys.argv[2], sys.argv[4], password=sys.argv[3][2:len(sys.argv[3])])
                    else:
                        debugPrint("Expected -p{password} argument, got '" + str(sys.argv[3]) +
                                   "' instead. See tusab -h. Aborting...")
                        sys.exit(PASSWORD_REQUIRED)
                else:
                    exploitDownload(drive, sys.argv[2], sys.argv[3])

            elif command == "-u":

                if sys.argv.__len__() < 4:
                    debugPrint("Invalid number of command line arguments for -u, see tusab -h. Aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                start = 4 if sys.argv[3][0:2] == "-p" else 3

                for i in range(start, sys.argv.__len__()):
                    if not os.path.exists(sys.argv[i]):
                        debugPrint("File '" + sys.argv[i] + "' does not exist. see tusab -h. Aborting...")
                        sys.exit(INVALID_COMMAND_LINE_PATH)

                exploitUpload(drive, sys.argv[2], sys.argv[start:sys.argv.__len__()],
                              sys.argv[3][2:len(sys.argv[3])] if sys.argv[3][0:2] == "-p" else None)

            elif command == "-l":
                if sys.argv.__len__() != 2:
                    debugPrint("Invalid number of command line arguments for -l, see tusab -h. Aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                outputPrint(json.dumps(exploitList(drive)))

            elif command == "-p":
                if sys.argv.__len__() != 2:
                    debugPrint("Invalid number of command line arguments for -p, see tusab -h. Aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                outputPrint("{ \"prefix\": \"" + str(exploitPrefix(drive)) + "\" }")

            elif command == "-r":
                if sys.argv.__len__() != 3:
                    debugPrint("Invalid number of command line arguments for -r, see tusab -h. Aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                exploitRemove(drive, sys.argv[2])

            elif command == "-f":
                if sys.argv.__len__() != 2:
                    debugPrint("Invalid number of command line arguments for -f, see tusab -h. Aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                exploitFlush()

            elif command == "-h":

                outputPrint("Usage:    tusab.exe -d TITLE [-p{PASSWORD}] FOLDER")
                outputPrint("          tusab.exe -u TITLE [-p{PASSWORD}] FOLDER/FILE1 [FOLDER/FILE2 ...]")
                outputPrint("          tusab.exe -l")
                outputPrint("          tusab.exe -r TITLE")
                outputPrint("          tusab.exe -p")
                outputPrint("          tusab.exe -h")
                outputPrint("          tusab.exe -f")
                outputPrint("")
                outputPrint("Commands: -d Download TITLE to FOLDER location, with optional PASSWORD")
                outputPrint("          -u Upload File/Folder list as TITLE to Drive, with optional PASSWORD")
                outputPrint("          -l List all tusab uploads with metadata")
                outputPrint("          -r Remove TITLE from uploads")
                outputPrint("          -p Output image prefix (used for searching and deletion from Google Photos)")
                outputPrint("          -h Deletes files in temporary folder created by the same parent process")
                outputPrint("          -h Print this help message")

    except TusabException as exc:
        debugPrint(str(exc) + "\nAborting...")
        unlock(drive)
        sys.exit(exc.code)

    finally:


        pass


if __name__ == '__main__':
    main()
