# TODO: .load() -> 5.6 sec/million
# TODO: option to print out key/value pairs while loading
# TODO: ability for user to auto-raise error on missing values
# TODO: alternate class that always reads from the file?
# TODO: add more filler functions like remove_section
# TODO: use getSection less?
# TODO: work out sectionLock with dot notation + load() + etc.
# TODO: low memory mode -> bettersectionproxy, attributes, etc.
# TODO: could __/___ cause issues with the way it gets renamed?
# TODO: errors with capitalization of options with dot notation?
# TODO: base load()'s type on fallback or do try/excepts with typecasts?

import configparser, sys

class LockedNameException(Exception):
    def __init__(self, name):
        self.name = name
    def __str__(self):
        return f'Option name "{self.name}" is not allowed ' \
                '(___parser, ___section, ___filepath, ' \
                '___sectionLock, ___defaultExtension).'

class SetSectionToValueError(Exception):
    def __init__(self, name):
        self.name = name
    def __str__(self):
        return f'Setting a section ("{self.name}") to a value is not allowed.'

class InvalidSectionError(Exception):
    def __init__(self, name, caller):
        self.name = name
        self.caller = caller
    def __str__(self):
        return f'{self.caller}: "{self.name}" is not a valid section.'



class BetterSectionProxy:
    def __init__(self, parent, section):
        self.___parent = parent
        self.___section = self.___parent.getParser()[section]

    def __setattr__(self, name, val):
        if name[:19] != '_BetterSectionProxy':
            self.___section[name] = str(val)
            self.___parent.__dict__[name] = val
        else:
            self.__dict__[name] = val

    def __getattr__(self, name):
        try: return self.___parent.__dict__[name]
        except: return self.___section[name]



class ConfigParseBetter:
    ___sectionLock = False
    ___errorForMissingFallbacks = True
    ___defaultExtension = '.ini'    # unused
    ___lowMemoryMode = False

    def __init__(self, filepath=None, ConfigParserObject=None, autoRead=True):
        # ConfigParserObject defaults to None because using objects as default
        # values will always init them first, causing 2 ConfigParserObjects to
        # be generated if the user passes in their own.
        if ConfigParserObject is None:
            self.___parser = configparser.ConfigParser()
        else:
            self.___parser = ConfigParserObject
        self.___section = 'DEFAULT'

        self.___filepath = filepath
        if not filepath:
            if sys.argv[0]:
                self.___filepath = sys.argv[0].split('\\')[-1][:-3]
            else:
                self.___filepath = 'config'
        if self.___filepath[-4:] not in ('.ini', '.cfg'):
            self.___filepath += self.___defaultExtension
        if autoRead:
            self.read(self.___filepath)

    def read(self, filepath=None, setSection=None):
        if setSection: self.setSection(setSection)
        filepath = filepath if filepath else self.___filepath
        self.___parser.read(filepath)

    def write(self, filepath=None):
        filepath = filepath if filepath else self.___filepath
        with open(filepath, 'w') as configfile:
            self.___parser.write(configfile)

    def refresh(self, ConfigParserObject=None, autoRead=True):
        oldSection = self.__dict__['_ConfigParseBetter___section'].name
        del self.___parser
        if ConfigParserObject is None:
            self.___parser = configparser.ConfigParser()
        else:
            self.___parser = ConfigParserObject
        if autoRead:
            self.read(self.___filepath)
        self.setSection(oldSection)

    def reset(self, ConfigParserObject=None, autoRead=True):
        toDelete = [k for k in self.__dict__ if k[:18] != '_ConfigParseBetter']
        for key in toDelete:
            del self.__dict__[key]
        self.refresh(ConfigParserObject, autoRead)

    def read_dict(self, dictionary, *args, **kwargs):
        self.___parser.read_dict(dictionary, *args, **kwargs)

    def read_file(self, file, *args, **kwargs):
        self.___parser.read_file(file, *args, **kwargs)

    def read_string(self, string, *args, **kwargs):
        self.___parser.read_string(string, *args, **kwargs)

    def load(self, key, fallback='', section=None):
        section, value = self._load(key, fallback, section)
        section[key] = str(value)   # 1.0595 sec/million
        self.__dict__[key] = value  # 0.1276 sec/million
        return value

    def loadFrom(self, section, key, fallback=''):
        return self.load(key, fallback, section)

    def loadAllFromSection(self, section=None, fallback='',
                           name=None, returnKey=False):
        # TODO: If load() is called before setSection(), this will start
        #       returning the settings loaded without a section, even
        #       though they should be loaded into the 'DEFAULT' section.
        section = self.getSection(section)
        if name:
            for sectionKey in self.___parser.options(section.name):
                if sectionKey.startswith(name):
                    if returnKey:
                        yield sectionKey, self.load(sectionKey, fallback, section)
                    else:
                        yield self.load(sectionKey, fallback, section)
        else:
            for sectionKey in self.___parser.options(section.name):
                if returnKey:
                    yield sectionKey, self.load(sectionKey, fallback, section)
                else:
                    yield self.load(sectionKey, fallback, section)

    def _load(self, key, fallback, section=None, verifySection=True):
        if key[:3] == '___':
            raise LockedNameException(key)
        if verifySection:
            section = self.getSection(section)
        if section.name in self.___parser.sections():
            try:
                if type(fallback) == bool:
                    return section, section.getboolean(key, fallback=fallback)
                elif type(fallback) == int:
                    return section, section.getint(key, fallback=fallback)
                elif type(fallback) == float:
                    return section, section.getfloat(key, fallback=fallback)
                return section, section.get(key, fallback=fallback)
            except:
                return section, fallback
        elif not self.___sectionLock:
            return section, self._loadFromAnywhere(key, fallback)
        else:
            return section, fallback    # add elif for raising error here?

    def _loadFromAnywhere(self, key, fallback):
        for section in self.___parser.sections():
            for sectionKey in self.___parser.options(section):
                if sectionKey == key.lower():
                    return self.___parser[section][sectionKey]
        return fallback

    def save(self, key, *values, delimiter=',', section=None):
        section = self.getSection(section)
        valueStr = delimiter.join(str(value) for value in values)
        #section[key] = valueStr     # TODO do time test here
        self.___parser.set(section.name, str(key), valueStr)
        self.__dict__[key] = values

    def saveTo(self, section, key, *values, delimiter=','):
        self.save(key, *values, delimiter=delimiter, section=section)

    def sections(self, name=None):
        if name: self._sectionsByName(name)
        else: return self.___parser.sections()

    def _sectionsByName(self, name):
        for section in self.___parser.sections():
            if section.startswith(name):
                yield section

    def removeSection(self, section):
        section = self.getSection(section)
        self.___parser.remove_section(section.name)

    def deleteSection(self, section):
        self.removeSection(section)

    def remove_section(self, section):
        self.removeSection(section)

    def copySection(self, section, newSection, deleteOld=False):
        section = self.getSection(section)
        newSection = self.getSection(newSection)
        self.setSection(newSection)
        for key, value in section.items():
            self.___parser.set(newSection.name, key, value)
        if deleteOld:
            self.___parser.remove_section(section.name)

    def renameSection(self, section, newSection):
        self.copySection(section, newSection, deleteOld=True)

    def setSection(self, section, locked=False):    # TODO locked
        self.___section = self.getSection(section)

    def getSection(self, section=None): # could this be faster?
        # TODO test try/except vs if statements for checking for sections
        if section is None:
            if self.___section is None:
                try:
                    section = self.___parser['DEFAULT']
                except:
                    self.___parser['DEFAULT'] = {}
                    section = self.___parser['DEFAULT']
            else:
                section = self.___section

        if isinstance(section, configparser.SectionProxy):
            try:
                return section
            except KeyError:
                name = section.name
                section = {}
                self.__dict__[name] = BetterSectionProxy(self, name)
                return section
        else:
            try:
                return self.___parser[section]
            except KeyError:
                self.___parser[section] = {}
                self.__dict__[section] = BetterSectionProxy(self, section)
                return self.___parser[section]

    def getParser(self):
        return self.___parser

    def getFilepath(self):
        return self.___filepath

    def getOptions(self, section):
        try:
            section = section if type(section) == str else section.name
            return self.___parser.options(section)
        except:
            raise InvalidSectionError(section, 'getOptions')

    def getItems(self, section):
        try:
            section = section if type(section) == str else section.name
            return self.___parser.items(section)
        except:
            raise InvalidSectionError(section, 'getItems')

    def __getitem__(self, key):
        try: return self.___parser[key]
        except: return None

    def __setitem__(self, key, val):
        self.___parser[key] = val

    def __getattr__(self, name):
        if name in self.sections():
            return BetterSectionProxy(self, name)
        return self._loadFromAnywhere(key=name, fallback=None)

    def __enter__(self):
        self.read()
        return self

    def __exit__(self, type, value, traceback):
        self.write()