import os
import logging
import ntpath

# This code comes partly / with minor mods from https://github.com/denyhosts/denyhosts/blob/master/DenyHosts/filetracker.py
# In accordance with § 31 odst. 1 písm. a) zákona č. 121/2000 Sb., autorský zákon

debug = logging.getLogger("filetracker").debug

OFFSET_APPEND = "._offset"

class FileTracker(object):
    def __init__(self, logfile, retroactive = True):
        self.work_dir = os.path.dirname(os.path.realpath(__file__)) + '/data'
        #print(self.work_dir)
        self.logfile = logfile
        self.retroactive = retroactive

        self.offset_file = ''.join([ntpath.basename(logfile), OFFSET_APPEND])
        #print("OFFSET FILE -> {}".format(self.offset_file))

        (self.__first_line, self.__offset) = self.__get_current_offset()



    def __get_last_offset(self):
        path = os.path.join(self.work_dir, self.offset_file)
        first_line = ""
        offset = 0
        try:
            fp = open(path, "r")
            first_line = fp.readline()[:-1]
            offset = int(fp.readline())
        except IOError:
            # print("\nRetroactive = {}".format(self.retroactive))
            # Retroactive param in config file is set to False
            if self.retroactive == False:
                try:
                    path = os.path.join(self.work_dir + "/..", self.logfile)
                    fp = open(path, "rb")
                    fp.seek(0, os.SEEK_END)
                    offset = fp.tell()
                    self.__offset = fp.tell()

                    fp.seek(0, 0)
                    self.__first_line = fp.readline().decode()[:-1]
                    first_line = self.__first_line
                    #print(self.__first_line)

                    # GET LAST LINE
                    # fp.seek(-2, os.SEEK_END)
                    # while fp.read(1) != b'\n':
                    #     fp.seek(-2, os.SEEK_CUR)
                    # self.__first_line = fp.readline().decode()[:-1]
                    # first_line = self.__first_line
                    # print(self.__first_line)

                    # Save the offset, else the offset file would never be created
                    self.save_offset(offset)
                except IOError as e:
                    #raise e
                    pass
                pass
            pass

        debug("__get_last_offset():")
        debug("   first_line: %s", first_line)
        debug("   offset: %ld", offset)

        return first_line, offset

    def __get_current_offset(self):
        first_line = ""
        offset = 0
        try:
            path = os.path.join(self.work_dir + "/..", self.logfile)
            fp = open(path, "r")
            first_line = fp.readline()[:-1]
            fp.seek(0, 2)
            offset = fp.tell()
        except IOError as e:
            print("EXCEPTION: {}".format(e))
            pass

        debug("__get_current_offset():")
        debug("   first_line: %s", first_line)
        debug("   offset: %ld", offset)

        return first_line, offset

    def update_first_line(self):
        first_line = ""
        try:
            fp = open(self.logfile, "r")
            first_line = fp.readline()[:-1]
        except IOError as e:
            raise e

        self.__first_line = first_line

    def get_offset(self):
        last_line, last_offset = self.__get_last_offset()

        if last_line != self.__first_line:
            # log file was rotated, start from beginning
            offset = 0
            #print("first")
        elif self.__offset > last_offset:
            # new lines exist in log file
            offset = last_offset
            #print("second")
        else:
            # no new entries in log file
            offset = None
            #print("third")

        debug("get_offset():")
        debug("   offset: %s", str(offset))

        return offset

    def save_offset(self, offset):
        path = os.path.join(self.work_dir, self.offset_file)
        try:
            fp = open(path, "w")
            fp.write("%s\n" % self.__first_line)
            fp.write("%ld\n" % offset)
            fp.close()
        except IOError:
            print("Could not save logfile offset to: %s" % path)
