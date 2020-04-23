
# Return error codes
UNKNOWN_ERROR = -1
INVALID_NUMBER_OF_COMMAND_LINE_ARGUMENTS = -2
INVALID_COMMAND_LINE_ARGUMENTS = -3
MULTIPLE_METADATA_FOLDERS_FOUND = -4
MULTIPLE_METADATA_FILES_FOUND = -5
METADATA_FILE_NOT_FOUND = -6
METADATA_FILE_NOT_LOADED = -7
MAGICK_CONVERT_FAILED = -8
TOBMP_CONVERT_FAILED = -9
SEVEN_ZIP_CONVERT_FAILED = -10
TITLE_ALREADY_EXISTS = -11
UPLOAD_TIMEOUT = -12
INVALID_COMMAND_LINE_PATH = -13
TITLE_DOES_NOT_EXIST = -14


class TusabException(Exception):
    def __init__(self, name, code, message="", args=tuple()):
        self.name = name
        self.message = message
        self.args = args
        self.code = code

    def __str__(self):
        return str(self.name) + " - '" + str(self.message) + "' " + str(self.args) + " Code " + str(self.code) + "."


class MultipleFoldersFoundError(TusabException):
    def __init__(self, message="", *args):
        super().__init__("MultipleFoldersFoundError", MULTIPLE_METADATA_FOLDERS_FOUND, message, args)


class MultipleMetadataFilesFoundError(TusabException):
    def __init__(self, message="", *args):
        super().__init__("MultipleMetadataFilesFoundError", MULTIPLE_METADATA_FILES_FOUND, message, args)


class MetadataFileNotFoundError(TusabException):
    def __init__(self, message="", *args):
        super().__init__("MetadataFileNotFoundError", METADATA_FILE_NOT_FOUND, message, args)


class MetadataFileNotLoadedError(TusabException):
    def __init__(self, message="", *args):
        super().__init__("MetadataFileNotLoadedError", METADATA_FILE_NOT_LOADED, message, args)


class MagickConvertFailedError(TusabException):
    def __init__(self, message="", *args):
        super().__init__("MagickConvertFailedError", MAGICK_CONVERT_FAILED, message, args)


class tobmpConvertFailedError(TusabException):
    def __init__(self, message="", *args):
        super().__init__("tobmpConvertFailedError", TOBMP_CONVERT_FAILED, message, args)


class SevenZipConvertFailedError(TusabException):
    def __init__(self, message="", *args):
        super().__init__("SevenZipConvertFailedError", SEVEN_ZIP_CONVERT_FAILED, message, args)


class TitleAlreadyExistsError(TusabException):
    def __init__(self, message="", *args):
        super().__init__("TitleAlreadyExistsError", TITLE_ALREADY_EXISTS, message, args)


class UploadTimeoutError(TusabException):
    def __init__(self, message="", *args):
        super().__init__("UploadTimeoutError", UPLOAD_TIMEOUT, message, args)


class TitleDoesNotExistError(TusabException):
    def __init__(self, message="", *args):
        super().__init__("TitleDoesNotExistError", TITLE_DOES_NOT_EXIST, message, args)

