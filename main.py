import time

from algorithms import *

import shutil

from googleapiclient.http import MediaIoBaseDownload

# Volume size ensures that resultant images are no larger than 16MP.
volume_size = 64 * 1000 * 1000 - 1000

# Config file stored on host (not in drive)
config = None


def exploitDownload(drive, title, folder):
    # Read Metadata
    metadata = loadMetadata(drive)['storage']['groups']

    imageList = None

    parentidentifier = str(getParentIdentifier())

    # Check title exists
    if title not in metadata:
        raise TitleDoesNotExistError("The title '" + str(title) + "' does not exist.", title, metadata)

    # Search through metadata list for 'file' then extract entry
    fileList = metadata[title]['images']

    # Make sure download files dont already exist in tmp location
    structure = metadata[title]['structure']['files']
    subitems = os.listdir(folder)
    conflicts = []

    for item in metadata[title]['structure']['folders']:
        structure.append(item['name'])

    for element in structure:
        if element in subitems:
            conflicts.append(element)

    if conflicts.__len__() != 0:
        raise OutputFilesAlreadyExist("The following files '" + str(conflicts) + "' already exist.", conflicts, folder)

    # Iterate over list of image names in group, download and convert back to archive volumes
    archiveVolumes = []

    for entry in fileList:

        request = drive.files().get_media(fileId=entry['id'])
        fh = open(config['temporary-file-path'] + "\\" + parentidentifier + "-" + entry['name'], "wb")

        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            debugPrint("Downloading " + entry['name'] + ": " + str(int(status.progress() * 100)) + "%.")

        fh.close()

        bmpName = entry['name'][0:-3] + "bmp"

        runProcess(MagickConvertFailedError, False, "magick", "convert",
                   config['temporary-file-path'] + "\\" + parentidentifier + "-" + entry['name'],
                   config['temporary-file-path'] + "\\" + parentidentifier + "-" + bmpName)

        os.remove(config['temporary-file-path'] + "\\" + parentidentifier + "-" + entry['name'])

        runProcess(tobmpConvertFailedError, False, "tobmp", config['temporary-file-path'] + "\\" + parentidentifier + "-" + bmpName)

        archiveVolumes.append(config['temporary-file-path'] + "\\" + parentidentifier + "-" + entry['name'][0:-4])

    # Extract archive
    runProcess(SevenZipConvertFailedError, False, "7z", "x", config['temporary-file-path'] + "\\" + parentidentifier + "-" + fileList[0]['name'][0:-4], "-o" + folder)

    # Delete archive volumes
    for file in archiveVolumes:
        os.remove(file)


def exploitUpload(drive, titleName, file_list):

    # Download metadata
    data = loadMetadata(drive)

    debugPrint("Metadata: " + json.dumps(data, indent=4))

    # Check titlename doesnt already exist
    if titleName in data['storage']['groups']:
        raise TitleAlreadyExistsError("Title chosen is already in use.", titleName)

    # Generate unique file name
    output_file_name = str(uuid.uuid4())

    parentidentifier = getParentIdentifier()

    # Add each file to archive
    runProcess(SevenZipConvertFailedError, False, "7z", "a", "-tzip", "-v" + str(volume_size),
               config['temporary-file-path'] + "\\" + parentidentifier + "-" + output_file_name + ".zip", *file_list)

    # Get list of all files and directories in tmp folder
    directory_list = os.listdir(config['temporary-file-path'])

    # Total size of input data, in bytes
    dataCount = 0

    # Iterate over all the generated archive volumes and convert to png, then move to B&S location
    index = 1
    while True:
        number_string = "{:03d}".format(index)
        file_part = parentidentifier + "-" + output_file_name + ".zip." + number_string
        prefix = data['storage']['prefix']
        debugPrint("file part: " + file_part)
        if directory_list.__contains__(file_part):
            res = runProcess(tobmpConvertFailedError, True, "tobmp", config['temporary-file-path'] + "\\" + file_part)

            dataCount += json.loads(str(res.stdout))['filesize']

            runProcess(MagickConvertFailedError, False, "magick", "convert", config['temporary-file-path'] + "\\" + parentidentifier + "-"
                       + output_file_name + ".zip." + number_string + ".bmp", config['temporary-file-path'] +
                       "\\" + parentidentifier + "-" + output_file_name + ".zip." + number_string + ".png")

            os.remove(config['temporary-file-path'] + "\\" + parentidentifier + "-" + output_file_name +
                      ".zip." + number_string + ".bmp")

            shutil.move(config['temporary-file-path'] + "\\" + parentidentifier + "-" + output_file_name +".zip." + number_string + ".png",
                        config['backup-and-sync-path'] + "\\" + prefix + "-" + output_file_name + ".zip." + number_string + ".png")

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
        imageFiles = drive.files().list(q="name='" + prefix + "-" + output_file_name + ".zip." + "{:03d}".format(search)
                                          + ".png'").execute()["files"]

        debugPrint(str([imageFiles, delay]))
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

        for i in range(1, count + 1):
            imageFiles = drive.files().list(q="name='" + prefix + "-" + output_file_name + ".zip." + "{:03d}".format(i)
                                              + ".png' and not trashed", fields="files(id,name)").execute()["files"]
            debugPrint(str([count, prefix + "-" + output_file_name + ".zip." + "{:03d}".format(i) + ".png", imageFiles, delay]))
            if imageFiles.__len__() == 1:
                imageFileList.append(imageFiles[0])
        if imageFileList.__len__() == count:
            break
        time.sleep(delay)
        delay = delay + 1

    # Delete the files from the B&S upload directory
    for i in range(1, count + 1):
        os.remove(config['backup-and-sync-path'] + "\\" + prefix + "-" + output_file_name + ".zip." +
                  "{:03d}".format(i) + ".png")

    # Modify dictionary
    data["storage"]["groups"][titleName] = {
        "images": imageFileList,
        "structure": fileStructure(file_list),
        "size": {
            "pixmap": None,      # Size of pixmap in bytes.
            "data": dataCount  # Total size of input data
        }
    }

    debugPrint("Added entry: " + json.dumps(data["storage"]["groups"][titleName], indent=4))

    # Upload metadata
    saveMetadata(drive, data)


# Return list of all uploads with their corresponding file structure
def exploitList(drive):

    # Open Metadata
    data = loadMetadata(drive)

    # Get list of all file groups
    return data['storage']['groups']


# Delete entry from drive
def exploitRemove(drive, title):

    # Open metadata
    data = loadMetadata(drive)

    # Check title exists
    if not title in data['storage']['groups']:
        raise TITLE_DOES_NOT_EXIST("The title '" + title + "' does not exist.", title, data['storage']['groups'])

    # Get 'title' element containing group data
    groups = data['storage']['groups'][title]['images']

    debugPrint(str(groups))

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
def exploitPrefix(drive):
    # Get metadata
    data = loadMetadata(drive)

    # Get and return prefix
    return data['storage']['prefix'] + "-"


# This function will delete all files in tmp created by this processes parent
def exploitFlush():

    # Get parent identifier
    parentIdentifier = getParentIdentifier()

    # Get list of all files generated by tuasb with the same parent id as this and delete
    completeList = os.listdir(config['temporary-file-path'])

    for file in completeList:
        if parentIdentifier in file:
            os.remove(config['temporary-file-path'] + "\\" + file)


# For testing purposes, not to be in final release
def deleteAll(drive):
    groups = loadMetadata(drive)['storage']['groups']

    for group in groups:
        exploitRemove(drive, group)


def main():

    global config

    debugPrint("Parent PID: " + str(os.getppid()))

    try:

        drive, config = exploitStartup()

        debugPrint("Prefix: " + str(exploitPrefix(drive)))

        debugPrint("Arguments: " + str(sys.argv))

        if sys.argv.__len__() < 2:
            debugPrint("Invalid command number of line arguments, aborting...")
            sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)
        else:
            command = sys.argv[1]
            if command == "-d":
                if sys.argv.__len__() != 4:
                    debugPrint("Invalid number of command line arguments for -d, aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                if not os.path.exists(sys.argv[3]):
                    debugPrint("Folder '" + sys.argv[3] + "' does not exist. Aborting...")

                exploitDownload(drive, sys.argv[2], sys.argv[3])

            elif command == "-u":

                if sys.argv.__len__() < 4:
                    debugPrint("Invalid number of command line arguments for -u, aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                for i in range(3, sys.argv.__len__()):
                    if not os.path.exists(sys.argv[i]):
                        debugPrint("File '" + sys.argv[i] + "' does not exist. Aborting...")
                        sys.exit(INVALID_COMMAND_LINE_PATH)

                exploitUpload(drive, sys.argv[2], sys.argv[3:sys.argv.__len__()])

            elif command == "-l":
                if sys.argv.__len__() != 2:
                    debugPrint("Invalid number of command line arguments for -l, aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                outputPrint(json.dumps(exploitList(drive)))

            elif command == "-p":
                if sys.argv.__len__() != 2:
                    debugPrint("Invalid number of command line arguments for -p, aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                outputPrint(exploitPrefix(drive))

            elif command == "-r":
                if sys.argv.__len__() != 3:
                    debugPrint("Invalid number of command line arguments for -r, aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                exploitRemove(drive, sys.argv[2])

            elif command == "-f":
                if sys.argv.__len__() != 2:
                    debugPrint("Invalid number of command line arguments for -f, aborting...")
                    sys.exit(INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS)

                exploitFlush()

            elif command == "-h":
                return

    except TusabException as exc:
        debugPrint(str(exc) + "\nAborting...")
        sys.exit(exc.code)

    finally:


        pass



if __name__ == '__main__':
    main()
