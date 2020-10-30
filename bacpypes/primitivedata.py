#!/usr/bin/python

"""
Primitive Data
"""

import sys
import time

from debugging import ModuleLogger

from errors import DecodingError
from pdu import *

# some debugging
_debug = 0
_log = ModuleLogger(globals())

def _str_to_hex(x, sep=''):
    return sep.join(["%02X" % (ord(c),) for c in x])

def _hex_to_str(x, sep=''):
    if sep:
        parts = x.split(sep)
    else:
        parts = [x[i:i+2] for i in range(0,len(x),2)]
    
    return ''.join([chr(int(part,16)) for part in parts])

#
#   Tag
#

class Tag(object):
    applicationTagClass     = 0
    contextTagClass         = 1
    openingTagClass         = 2
    closingTagClass         = 3

    nullAppTag              = 0
    booleanAppTag           = 1
    unsignedAppTag          = 2
    integerAppTag           = 3
    realAppTag              = 4
    doubleAppTag            = 5
    octetStringAppTag       = 6
    characterStringAppTag   = 7
    bitStringAppTag         = 8
    enumeratedAppTag        = 9
    dateAppTag              = 10
    timeAppTag              = 11
    objectIdentifierAppTag  = 12
    reservedAppTag13        = 13
    reservedAppTag14        = 14
    reservedAppTag15        = 15

    _app_tag_name = \
        [ 'null', 'boolean', 'unsigned', 'integer'
        , 'real', 'double', 'octetString', 'characterString'
        , 'bitString', 'enumerated', 'date', 'time'
        , 'objectIdentifier', 'reserved13', 'reserved14', 'reserved15'
        ]
    _app_tag_class = [] # defined later

    def __init__(self, *args):
        self.tagClass = None
        self.tagNumber = None
        self.tagLVT = None
        self.tagData = None

        if args:
            if (len(args) == 1) and isinstance(args[0], PDUData):
                self.decode(args[0])
            elif (len(args) >= 2):
                self.set(*args)
            else:
                raise ValueError, "invalid Tag ctor arguments"

    def set(self, tclass, tnum, tlvt=0, tdata=''):
        """set the values of the tag."""
        self.tagClass = tclass
        self.tagNumber = tnum
        self.tagLVT = tlvt
        self.tagData = tdata

    def set_app_data(self, tnum, tdata):
        """set the values of the tag."""
        self.tagClass = Tag.applicationTagClass
        self.tagNumber = tnum
        self.tagLVT = len(tdata)
        self.tagData = tdata

    def encode(self, pdu):
        # check for special encoding of open and close tags
        if (self.tagClass == Tag.openingTagClass):
            pdu.put(((self.tagNumber & 0x0F) << 4) + 0x0E)
            return
        if (self.tagClass == Tag.closingTagClass):
            pdu.put(((self.tagNumber & 0x0F) << 4) + 0x0F)
            return

        # check for context encoding
        if (self.tagClass == Tag.contextTagClass):
            data = 0x08
        else:
            data = 0x00

        # encode the tag number part
        if (self.tagNumber < 15):
            data += (self.tagNumber << 4)
        else:
            data += 0xF0

        # encode the length/value/type part
        if (self.tagLVT < 5):
            data += self.tagLVT
        else:
            data += 0x05

        # save this and the extended tag value
        pdu.put( data )
        if (self.tagNumber >= 15):
            pdu.put(self.tagNumber)

        # really short lengths are already done
        if (self.tagLVT >= 5):
            if (self.tagLVT <= 253):
                pdu.put( self.tagLVT )
            elif (self.tagLVT <= 65535):
                pdu.put( 254 )
                pdu.put_short( self.tagLVT )
            else:
                pdu.put( 255 )
                pdu.put_long( self.tagLVT )

        # now put the data
        pdu.put_data(self.tagData)

    def decode(self, pdu):
        tag = pdu.get()

        # extract the type
        self.tagClass = (tag >> 3) & 0x01

        # extract the tag number
        self.tagNumber = (tag >> 4)
        if (self.tagNumber == 0x0F):
            self.tagNumber = pdu.get()

        # extract the length
        self.tagLVT = tag & 0x07
        if (self.tagLVT == 5):
            self.tagLVT = pdu.get()
            if (self.tagLVT == 254):
                self.tagLVT = pdu.get_short()
            elif (self.tagLVT == 255):
                self.tagLVT = pdu.get_long()
        elif (self.tagLVT == 6):
            self.tagClass = Tag.openingTagClass
            self.tagLVT = 0
        elif (self.tagLVT == 7):
            self.tagClass = Tag.closingTagClass
            self.tagLVT = 0

        # application tagged boolean has no more data
        if (self.tagClass == Tag.applicationTagClass) and (self.tagNumber == Tag.booleanAppTag):
            # tagLVT contains value
            self.tagData = ''
        else:
            # tagLVT contains length
            self.tagData = pdu.get_data(self.tagLVT)

    def app_to_context(self, context):
        """Return a context encoded tag."""
        if self.tagClass != Tag.applicationTagClass:
            raise ValueError, "application tag required"

        # application tagged boolean now has data
        if (self.tagNumber == Tag.booleanAppTag):
            return ContextTag(context, chr(self.tagLVT))
        else:
            return ContextTag(context, self.tagData)

    def context_to_app(self, dataType):
        """Return an application encoded tag."""
        if self.tagClass != Tag.contextTagClass:
            raise ValueError, "context tag required"

        # context booleans have value in data
        if (dataType == Tag.booleanAppTag):
            return Tag(Tag.applicationTagClass, Tag.booleanAppTag, ord(self.tagData[0]), '')
        else:
            return ApplicationTag(dataType, self.tagData)

    def app_to_object(self):
        """Return the application object encoded by the tag."""
        if self.tagClass != Tag.applicationTagClass:
            raise ValueError, "application tag required"

        # get the class to build
        klass = self._app_tag_class[self.tagNumber]
        if not klass:
            return None

        # build an object, tell it to decode this tag, and return it
        return klass(self)

    def __repr__(self):
        xid = id(self)
        if (xid < 0): xid += (1L << 32)

        sname = self.__module__ + '.' + self.__class__.__name__
        try:
            if self.tagClass == Tag.openingTagClass:
                desc = "(open(%d))" % (self.tagNumber,)
            elif self.tagClass == Tag.closingTagClass:
                desc = "(close(%d))" % (self.tagNumber,)
            elif self.tagClass == Tag.contextTagClass:
                desc = "(context(%d))" % (self.tagNumber,)
            elif self.tagClass == Tag.applicationTagClass:
                desc = "(%s)" % (self._app_tag_name[self.tagNumber],)
            else:
                raise ValueError, "invalid tag class"
        except:
            desc = "(?)"

        return '<' + sname + desc + ' instance at 0x%08x' % (xid,) + '>'

    def __eq__(self, tag):
        return (self.tagClass == tag.tagClass) \
            and (self.tagNumber == tag.tagNumber) \
            and (self.tagLVT == tag.tagLVT) \
            and (self.tagData == tag.tagData)

    def __ne__(self,arg):
        return not self.__eq__(arg)

    def debug_contents(self, indent=1, file=sys.stdout, _ids=None):
        # object reference first
        file.write("%s%r\n" % ("    " * indent, self))
        indent += 1
        
        # tag class
        msg = "%stagClass = %s " % ("    " * indent, self.tagClass)
        if self.tagClass == Tag.applicationTagClass: msg += 'application'
        elif self.tagClass == Tag.contextTagClass: msg += 'context'
        elif self.tagClass == Tag.openingTagClass: msg += 'opening'
        elif self.tagClass == Tag.closingTagClass: msg += 'closing'
        else: msg += "?"
        file.write(msg + "\n")
        
        # tag number
        msg = "%stagNumber = %d " % ("    " * indent, self.tagNumber)
        if self.tagClass == Tag.applicationTagClass:
            try:
                msg += self._app_tag_name[self.tagNumber]
            except:
                msg += '?'
        file.write(msg + "\n")
        
        # length, value, type
        file.write("%stagLVT = %s\n" % ("    " * indent, self.tagLVT))
        
        # data
        file.write("%stagData = '%s'\n" % ("    " * indent, _str_to_hex(self.tagData,'.')))
    
#
#   ApplicationTag
#

class ApplicationTag(Tag):

    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], PDUData):
            Tag.__init__(self, args[0])
            if self.tagClass != Tag.applicationTagClass:
                raise DecodingError, "application tag not decoded"
        elif len(args) == 2:
            tnum, tdata = args
            Tag.__init__(self, Tag.applicationTagClass, tnum, len(tdata), tdata)
        else:
            raise ValueError, "ApplicationTag ctor requires a type and data or PDUData"

#
#   ContextTag
#

class ContextTag(Tag):

    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], PDUData):
            Tag.__init__(self, args[0])
            if self.tagClass != Tag.contextTagClass:
                raise DecodingError, "context tag not decoded"
        elif len(args) == 2:
            tnum, tdata = args
            Tag.__init__(self, Tag.contextTagClass, tnum, len(tdata), tdata)
        else:
            raise ValueError, "ContextTag ctor requires a type and data or PDUData"

#
#   OpeningTag
#

class OpeningTag(Tag):

    def __init__(self, context):
        if isinstance(context, PDUData):
            Tag.__init__(self, context)
            if self.tagClass != Tag.openingTagClass:
                raise DecodingError, "opening tag not decoded"
        elif isinstance(context, types.IntType):
            Tag.__init__(self, Tag.openingTagClass, context)
        else:
            raise TypeError, "OpeningTag ctor requires an integer or PDUData"

#
#   ClosingTag
#

class ClosingTag(Tag):

    def __init__(self, context):
        if isinstance(context, PDUData):
            Tag.__init__(self, context)
            if self.tagClass != Tag.closingTagClass:
                raise DecodingError, "closing tag not decoded"
        elif isinstance(context, types.IntType):
            Tag.__init__(self, Tag.closingTagClass, context)
        else:
            raise TypeError, "OpeningTag ctor requires an integer or PDUData"

#
#   TagList
#

class TagList(object):

    def __init__(self, arg=None):
        self.tagList = []

        if isinstance(arg, types.ListType):
            self.tagList = arg
        elif isinstance(arg, TagList):
            self.tagList = arg.tagList[:]
        elif isinstance(arg, PDUData):
            self.decode(arg)

    def append(self, tag):
        self.tagList.append(tag)

    def extend(self, taglist):
        self.tagList.extend(taglist)

    def __getitem__(self, item):
        return self.tagList[item]

    def __len__(self):
        return len(self.tagList)

    def Peek(self):
        """Return the tag at the front of the list."""
        if self.tagList:
            tag = self.tagList[0]
        else:
            tag = None

        return tag

    def push(self, tag):
        """Return a tag back to the front of the list."""
        self.tagList = [tag] + self.tagList

    def Pop(self):
        """Remove the tag from the front of the list and return it."""
        if self.tagList:
            tag = self.tagList[0]
            del self.tagList[0]
        else:
            tag = None

        return tag

    def get_context(self, context):
        """Return a tag or a list of tags context encoded."""
        # forward pass
        i = 0
        while i < len(self.tagList):
            tag = self.tagList[i]

            # skip application stuff
            if tag.tagClass == Tag.applicationTagClass:
                pass

            # check for context encoded atomic value
            elif tag.tagClass == Tag.contextTagClass:
                if tag.tagNumber == context:
                    return tag

            # check for context encoded group
            elif tag.tagClass == Tag.openingTagClass:
                keeper = tag.tagNumber == context
                rslt = []
                i += 1
                lvl = 0
                while i < len(self.tagList):
                    tag = self.tagList[i]
                    if tag.tagClass == Tag.openingTagClass:
                        lvl += 1
                    elif tag.tagClass == Tag.closingTagClass:
                        lvl -= 1
                        if lvl < 0: break

                    rslt.append(tag)
                    i += 1

                # make sure everything balances
                if lvl >= 0:
                    raise DecodingError, "mismatched open/close tags"

                # get everything we need?
                if keeper:
                    return TagList(rslt)
            else:
                raise DecodingError, "unexpected tag"

            # try the next tag
            i += 1

        # nothing found
        return None

    def encode(self, pdu):
        """encode the tag list into a PDU."""
        for tag in self.tagList:
            tag.encode(pdu)

    def decode(self, pdu):
        """decode the tags from a PDU."""
        while pdu.pduData:
            self.tagList.append( Tag(pdu) )

    def debug_contents(self, indent=1, file=sys.stdout, _ids=None):
        for tag in self.tagList:
            tag.debug_contents(indent+1, file, _ids)
            
#
#   Atomic
#

class Atomic(object):

    _app_tag = None

    def __cmp__(self, other):
        # hoop jump it
        if not isinstance(other, self.__class__):
            other = self.__class__(other)

        # now compare the values
        if (self.value < other.value):
            return -1
        elif (self.value > other.value):
            return 1
        else:
            return 0

#
#   Null
#

class Null(Atomic):

    _app_tag = Tag.nullAppTag

    def __init__(self, arg=None):
        self.value = ()

        if arg is None:
            pass
        elif isinstance(arg,Tag):
            self.decode(arg)
        elif isinstance(arg,types.TupleType):
            if len(arg) != 0:
                raise ValueError, "empty tuple required"
        elif isinstance(arg, Null):
            pass
        else:
            raise TypeError, "invalid constructor datatype"

    def encode(self, tag):
        tag.set_app_data(Tag.nullAppTag, '')

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.nullAppTag):
            raise ValueError, "null application tag required"

        self.value = ()

    def __str__(self):
        return "Null"

#
#   Boolean
#

class Boolean(Atomic):

    _app_tag = Tag.booleanAppTag

    def __init__(self, arg=None):
        self.value = False

        if arg is None:
            pass
        elif isinstance(arg,Tag):
            self.decode(arg)
        elif isinstance(arg,types.BooleanType):
            self.value = arg
        elif isinstance(arg, Boolean):
            self.value = arg.value
        else:
            raise TypeError, "invalid constructor datatype"

    def encode(self, tag):
        tag.set(Tag.applicationTagClass, Tag.booleanAppTag, int(self.value), '')

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.booleanAppTag):
            raise ValueError, "boolean application tag required"

        # get the data
        self.value = bool(tag.tagLVT)

    def __str__(self):
        return "Boolean(%s)" % (str(self.value), )

#
#   Unsigned
#

class Unsigned(Atomic):

    _app_tag = Tag.unsignedAppTag

    def __init__(self,arg = None):
        self.value = 0L

        if arg is None:
            pass
        elif isinstance(arg,Tag):
            self.decode(arg)
        elif isinstance(arg,types.IntType):
            if (arg < 0):
                raise ValueError, "unsigned integer required"
            self.value = long(arg)
        elif isinstance(arg,types.LongType):
            if (arg < 0):
                raise ValueError, "unsigned integer required"
            self.value = arg
        elif isinstance(arg, Unsigned):
            self.value = arg.value
        else:
            raise TypeError, "invalid constructor datatype"

    def encode(self, tag):
        # rip apart the number
        data = [ord(c) for c in struct.pack('>L',self.value)]

        # reduce the value to the smallest number of octets
        while (len(data) > 1) and (data[0] == 0):
            del data[0]

        # encode the tag
        tag.set_app_data(Tag.unsignedAppTag, ''.join(chr(c) for c in data))

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.unsignedAppTag):
            raise ValueError, "unsigned application tag required"

        # get the data
        rslt = 0L
        for c in tag.tagData:
            rslt = (rslt << 8) + ord(c)

        # save the result
        self.value = rslt

    def __str__(self):
        return "Unsigned(%s)" % (self.value, )

#
#   Integer
#

class Integer(Atomic):

    _app_tag = Tag.integerAppTag

    def __init__(self,arg = None):
        self.value = 0

        if arg is None:
            pass
        elif isinstance(arg,Tag):
            self.decode(arg)
        elif isinstance(arg,types.IntType):
            self.value = arg
        elif isinstance(arg,types.LongType):
            self.value = arg
        elif isinstance(arg, Integer):
            self.value = arg.value
        else:
            raise TypeError, "invalid constructor datatype"

    def encode(self, tag):
        # rip apart the number
        data = [ord(c) for c in struct.pack('>I', (self.value & 0xFFFFFFFF))]

        # reduce the value to the smallest number of bytes, be
        # careful about sign extension
        if self.value < 0:
            while (len(data) > 1):
                if (data[0] != 255):
                    break
                if (data[1] < 128):
                    break
                del data[0]
        else:
            while (len(data) > 1):
                if (data[0] != 0):
                    break
                if (data[1] >= 128):
                    break
                del data[0]

        # encode the tag
        tag.set_app_data(Tag.integerAppTag, ''.join(chr(c) for c in data))

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.integerAppTag):
            raise ValueError, "integer application tag required"

        # get the data
        rslt = ord(tag.tagData[0])
        if (rslt & 0x80) != 0:
            rslt = (-1 << 8) | rslt

        for c in tag.tagData[1:]:
            rslt = (rslt << 8) | ord(c)

        # save the result
        self.value = rslt

    def __str__(self):
        return "Integer(%s)" % (self.value, )

#
#   Real
#

class Real(Atomic):

    _app_tag = Tag.realAppTag

    def __init__(self, arg=None):
        self.value = 0.0

        if arg is None:
            pass
        elif isinstance(arg,Tag):
            self.decode(arg)
        elif isinstance(arg,types.FloatType):
            self.value = arg
        elif isinstance(arg,types.IntType) or isinstance(arg,types.LongType):
            self.value = float(arg)
        elif isinstance(arg, Real):
            self.value = arg.value
        else:
            raise TypeError, "invalid constructor datatype"

    def encode(self, tag):
        # encode the tag
        tag.set_app_data(Tag.realAppTag, struct.pack('>f',self.value))

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.realAppTag):
            raise ValueError, "real application tag required"

        # extract the data
        self.value = struct.unpack('>f',tag.tagData)[0]

    def __str__(self):
        return "Real(%g)" % (self.value,)

#
#   Double
#

class Double(Atomic):

    _app_tag = Tag.doubleAppTag

    def __init__(self,arg = None):
        self.value = 0.0

        if arg is None:
            pass
        elif isinstance(arg,Tag):
            self.decode(arg)
        elif isinstance(arg,types.FloatType):
            self.value = arg
        elif isinstance(arg,types.IntType) or isinstance(arg,types.LongType):
            self.value = float(arg)
        elif isinstance(arg, Double):
            self.value = arg.value
        else:
            raise TypeError, "invalid constructor datatype"

    def encode(self, tag):
        # encode the tag
        tag.set_app_data(Tag.doubleAppTag, struct.pack('>d',self.value))

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.doubleAppTag):
            raise ValueError, "double application tag required"

        # extract the data
        self.value = struct.unpack('>d',tag.tagData)[0]

    def __str__(self):
        return "Double(%g)" % (self.value,)

#
#   OctetString
#

class OctetString(Atomic):

    _app_tag = Tag.octetStringAppTag

    def __init__(self, arg=None):
        self.value = ''

        if arg is None:
            pass
        elif isinstance(arg,Tag):
            self.decode(arg)
        elif isinstance(arg,types.StringType):
            self.value = arg
        elif isinstance(arg, OctetString):
            self.value = arg.value
        else:
            raise TypeError, "invalid constructor datatype"

    def encode(self, tag):
        # encode the tag
        tag.set_app_data(Tag.octetStringAppTag, self.value)

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.octetStringAppTag):
            raise ValueError, "octet string application tag required"

        self.value = tag.tagData

    def __str__(self):
        return "OctetString(X'" + _str_to_hex(self.value) + "')"

#
#   CharacterString
#

class CharacterString(Atomic):

    _app_tag = Tag.characterStringAppTag

    def __init__(self, arg=None):
        self.value = ''
        self.strEncoding = 0
        self.strValue = ''

        if arg is None:
            pass
        elif isinstance(arg,Tag):
            self.decode(arg)
        elif isinstance(arg,types.StringType):
            self.strValue = self.value = arg
        elif isinstance(arg,types.UnicodeType):
            self.strValue = self.value = str(arg)
        elif isinstance(arg, CharacterString):
            self.value = arg.value
            self.strEncoding = arg.strEncoding
            self.strValue = arg.strValue
        else:
            raise TypeError, "invalid constructor datatype"

    def encode(self, tag):
        # encode the tag
        tag.set_app_data(Tag.characterStringAppTag, chr(self.strEncoding)+self.strValue)

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.characterStringAppTag):
            raise ValueError, "character string application tag required"

        # extract the data
        self.strEncoding = ord(tag.tagData[0])
        self.strValue = tag.tagData[1:]

        # normalize the value
        if (self.strEncoding == 0):
            udata = self.strValue.decode('utf_8')
            self.value = str(udata.encode('ascii', 'backslashreplace'))
        elif (self.strEncoding == 3):
            udata = self.strValue.decode('utf_32be')
            self.value = str(udata.encode('ascii', 'backslashreplace'))  
        elif (self.strEncoding == 4):
            udata = self.strValue.decode('utf_16be')
            self.value = str(udata.encode('ascii', 'backslashreplace'))
        elif (self.strEncoding == 5):
            udata = self.strValue.decode('latin_1')
            self.value = str(udata.encode('ascii', 'backslashreplace'))
        else:
            self.value = '### unknown encoding: %d ###' % (self.strEncoding,)
 
    def __str__(self):
        return "CharacterString(%d," % (self.strEncoding,) + repr(self.strValue) + ")"

#
#   BitString
#

class BitString(Atomic):

    _app_tag = Tag.bitStringAppTag
    bitNames = {}
    bitLen = 0

    def __init__(self, arg = None):
        self.value = [0] * self.bitLen

        if arg is None:
            pass
        elif isinstance(arg,Tag):
            self.decode(arg)
        elif isinstance(arg,types.ListType):
            allInts = allStrings = True
            for elem in arg:
                allInts = allInts and ((elem == 0) or (elem == 1))
                allStrings = allStrings and self.bitNames.has_key(elem)

            if allInts:
                self.value = arg
            elif allStrings:
                for bit in arg:
                    bit = self.bitNames[bit]
                    if (bit < 0) or (bit > len(self.value)):
                        raise IndexError, "constructor element out of range"
                    self.value[bit] = 1
            else:
                raise TypeError, "invalid constructor list element(s)"
        elif isinstance(arg,BitString):
            self.value = arg.value[:]
        else:
            raise TypeError, "invalid constructor datatype"

    def encode(self, tag):
        # compute the unused bits to fill out the string
        _, used = divmod(len(self.value), 8)
        unused = used and (8 - used) or 0

        # start with the number of unused bits
        data = chr(unused)

        # build and append each packed octet
        bits = self.value + [0] * unused
        for i in range(0,len(bits),8):
            x = 0
            for j in range(0,8):
                x |= bits[i + j] << (7 - j)
            data += chr(x)

        # encode the tag
        tag.set_app_data(Tag.bitStringAppTag, data)

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.bitStringAppTag):
            raise ValueError, "bit string application tag required"

        # extract the number of unused bits
        unused = ord(tag.tagData[0])

        # extract the data
        data = []
        for c in tag.tagData[1:]:
            x = ord(c)
            for i in range(8):
                if (x & (1 << (7 - i))) != 0:
                    data.append( 1 )
                else:
                    data.append( 0 )

        # trim off the unused bits
        if unused:
            self.value = data[:-unused]
        else:
            self.value = data
            
    def __str__(self):
        # flip the bit names
        bitNames = {}
        for key, value in self.bitNames.iteritems():
            bitNames[value] = key

        # build a list of values and/or names
        valueList = []
        for value, index in zip(self.value,range(len(self.value))):
            if bitNames.has_key(index):
                if value:
                    valueList.append(bitNames[index])
                else:
                    valueList.append('!' + bitNames[index])
            else:
                valueList.append(str(value))

        # bundle it together
        return "BitString(" + ','.join(valueList) + ")"

    def __getitem__(self, bit):
        if isinstance(bit,types.IntType):
            pass
        elif isinstance(bit,types.StringType):
            if not self.bitNames.has_key(bit):
                raise IndexError, "unknown bit name '%s'" % (bit,)

            bit = self.bitNames[bit]
        else:
            raise TypeError, "bit index must be an integer or bit name"

        if (bit < 0) or (bit > len(self.value)):
            raise IndexError, "list index out of range"

        return self.value[bit]

    def __setitem__(self, bit, value):
        if isinstance(bit,types.IntType):
            pass
        elif isinstance(bit,types.StringType):
            if not self.bitNames.has_key(bit):
                raise IndexError, "unknown bit name '%s'" % (bit,)

            bit = self.bitNames[bit]
        else:
            raise TypeError, "bit index must be an integer or bit name"

        if (bit < 0) or (bit > len(self.value)):
            raise IndexError, "list index out of range"

        # funny cast to a bit
        self.value[bit] = value and 1 or 0

#
#   Enumerated
#

class Enumerated(Atomic):

    _app_tag = Tag.enumeratedAppTag

    enumerations = {}
    _xlate_table = {}

    def __init__(self, arg=None):
        self.value = 0L

        # see if the class has a translate table
        if not self.__class__.__dict__.has_key('_xlate_table'):
            expand_enumerations(self.__class__)

        # initialize the object
        if arg is None:
            pass
        elif isinstance(arg, Tag):
            self.decode(arg)
        elif isinstance(arg, types.IntType):
            if (arg < 0):
                raise ValueError, "unsigned integer required"

            # convert it to a string if you can
            try: self.value = self._xlate_table[arg]
            except KeyError: self.value = long(arg)
        elif isinstance(arg, types.LongType):
            if (arg < 0):
                raise ValueError, "unsigned integer required"

            # convert it to a string if you can
            try: self.value = self._xlate_table[arg]
            except KeyError: self.value = long(arg)
        elif isinstance(arg,types.StringType):
            if self._xlate_table.has_key(arg):
                self.value = arg
            else:
                raise ValueError, "undefined enumeration '%s'" % (arg,)
        elif isinstance(arg, Enumerated):
            self.value = arg.value
        else:
            raise TypeError, "invalid constructor datatype"

    def __getitem__(self, item):
        return self._xlate_table.get(item)

    def get_long(self):
        if isinstance(self.value, types.LongType):
            return self.value
        elif isinstance(self.value, types.StringType):
            return long(self._xlate_table[self.value])
        else:
            raise TypeError, "%s is an invalid enumeration value datatype" % (type(self.value),)

    def keylist(self):
        """Return a list of names in order by value."""
        items = self.enumerations.items()
        items.sort(lambda a, b: cmp(a[1], b[1]))

        # last item has highest value
        rslt = [None] * (items[-1][1] + 1)

        # map the values
        for key, value in items:
            rslt[value] = key

        # return the result
        return rslt

    def __cmp__(self, other):
        """Special function to make sure comparisons are done in enumeration
        order, not alphabetic order."""
        # hoop jump it
        if not isinstance(other, self.__class__):
            other = self.__class__(other)

        # get the numeric version
        a = self.get_long()
        b = other.get_long()

        # now compare the values
        if (a < b):
            return -1
        elif (a > b):
            return 1
        else:
            return 0

    def encode(self, tag):
        if isinstance(self.value, types.IntType):
            value = long(self.value)
        if isinstance(self.value, types.LongType):
            value = self.value
        elif isinstance(self.value, types.StringType):
            value = self._xlate_table[self.value]
        else:
            raise TypeError, "%s is an invalid enumeration value datatype" % (type(self.value),)

        # rip apart the number
        data = [ord(c) for c in struct.pack('>L',value)]

        # reduce the value to the smallest number of octets
        while (len(data) > 1) and (data[0] == 0):
            del data[0]

        # encode the tag
        tag.set_app_data(Tag.enumeratedAppTag, ''.join(chr(c) for c in data))

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.enumeratedAppTag):
            raise ValueError, "enumerated application tag required"

        # get the data
        rslt = 0L
        for c in tag.tagData:
            rslt = (rslt << 8) + ord(c)

        # convert it to a string if you can
        try: rslt = self._xlate_table[rslt]
        except KeyError: pass

        # save the result
        self.value = rslt

    def __str__(self):
        return "Enumerated(%s)" % (self.value,)

#
#   expand_enumerations
#

# translate lowers to uppers, keep digits, toss everything else
_expand_translate_table = ''.join([c.isalnum() and c.upper() or '-' for c in [chr(cc) for cc in range(256)]])
_expand_delete_chars = ''.join([chr(cc) for cc in range(256) if not chr(cc).isalnum()])
del c, cc

def expand_enumerations(klass):
    # build a value dictionary
    xlateTable = {}
    for name, value in klass.enumerations.iteritems():
        # save the results
        xlateTable[name] = value
        xlateTable[value] = name

        # translate the name for a class const
        name = name.translate(_expand_translate_table, _expand_delete_chars)

        # save the name in the class
        setattr(klass, name, value)

    # save the dictionary in the class
    setattr(klass, '_xlate_table', xlateTable)

#
#   Date
#

class Date(Atomic):

    _app_tag = Tag.dateAppTag

    DONT_CARE = 255

    def __init__(self, arg=None, year=255, month=255, day=255, dayOfWeek=255):
        self.value = (year, month, day, dayOfWeek)

        if arg is None:
            pass
        elif isinstance(arg,Tag):
            self.decode(arg)
        elif isinstance(arg, types.TupleType):
            self.value = arg
        elif isinstance(arg, Date):
            self.value = arg.value
        else:
            raise TypeError, "invalid constructor datatype"

    def now(self):
        tup = time.localtime()

        self.value = (tup[0]-1900, tup[1], tup[2], tup[6] + 1)

        return self

    def CalcDayOfWeek(self):
        """Calculate the correct day of the week."""
        # rip apart the value
        year, month, day, dayOfWeek = self.value

        # make sure all the components are defined
        if (year != 255) and (month != 255) and (day != 255):
            today = time.mktime( (year + 1900, month, day, 0, 0, 0, 0, 0, -1) )
            dayOfWeek = time.gmtime(today)[6] + 1

        # put it back together
        self.value = (year, month, day, dayOfWeek)

    def encode(self, tag):
        # encode the tag
        tag.set_app_data(Tag.dateAppTag, ''.join(chr(c) for c in self.value))

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.dateAppTag):
            raise ValueError, "date application tag required"

        # rip apart the data
        self.value = tuple(ord(c) for c in tag.tagData)

    def __str__(self):
        # rip it apart
        year, month, day, dayOfWeek = self.value

        rslt = "Date("
        if month == 255:
            rslt += "*/"
        else:
            rslt += "%d/" % (month,)
        if day == 255:
            rslt += "*/"
        else:
            rslt += "%d/" % (day,)
        if year == 255:
            rslt += "* "
        else:
            rslt += "%d " % (year + 1900,)
        if dayOfWeek == 255:
            rslt += "*)"
        else:
            rslt += ['','Mon','Tue','Wed','Thu','Fri','Sat','Sun'][dayOfWeek] + ")"

        return rslt

#
#   Time
#

class Time(Atomic):

    _app_tag = Tag.timeAppTag

    DONT_CARE = 255

    def __init__(self, arg=None, hour=255, minute=255, second=255, hundredth=255):
        # put it together
        self.value = (hour, minute, second, hundredth)

        if arg is None:
            pass
        elif isinstance(arg,Tag):
            self.decode(arg)
        elif isinstance(arg, types.TupleType):
            self.value = arg
        elif isinstance(arg, Time):
            self.value = arg.value
        else:
            raise TypeError, "invalid constructor datatype"

    def now(self):
        now = time.time()
        tup = time.localtime(now)

        self.value = (tup[3], tup[4], tup[5], int((now - int(now)) * 100))

        return self

    def encode(self, tag):
        # encode the tag
        tag.set_app_data(Tag.timeAppTag, ''.join(chr(c) for c in self.value))

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.timeAppTag):
            raise ValueError, "time application tag required"

        # rip apart the data
        self.value = tuple(ord(c) for c in tag.tagData)

    def __str__(self):
        # rip it apart
        hour, minute, second, hundredth = self.value

        rslt = "Time("
        if hour == 255:
            rslt += "*:"
        else:
            rslt += "%02d:" % (hour,)
        if minute == 255:
            rslt += "*:"
        else:
            rslt += "%02d:" % (minute,)
        if second == 255:
            rslt += "*."
        else:
            rslt += "%02d." % (second,)
        if hundredth == 255:
            rslt += "*)"
        else:
            rslt += "%02d)" % (hundredth,)

        return rslt

#
#   ObjectType
#

class ObjectType(Enumerated):
    vendor_range = (128, 1023)
    enumerations = \
        { 'accessDoor':30
        , 'accessPoint':33
        , 'accessRights':34
        , 'accessUser':35
        , 'accessZone':36
        , 'accumulator':23
        , 'analogInput':0
        , 'analogOutput':1
        , 'analogValue':2
        , 'averaging':18
        , 'binaryInput':3
        , 'binaryOutput':4
        , 'binaryValue':5
        , 'bitstringValue':39
        , 'calendar':6
        , 'characterstringValue':40
        , 'command':7
        , 'credentialDataInput':37
        , 'datePatternValue':41
        , 'dateValue':42
        , 'datetimePatternValue':43
        , 'datetimeValue':44
        , 'device':8
        , 'eventEnrollment':9
        , 'eventLog':25
        , 'file':10
        , 'globalGroup':26
        , 'group':11
        , 'integerValue':45
        , 'largeAnalogValue':46
        , 'lifeSafetyPoint':21
        , 'lifeSafetyZone':22
        , 'loadControl':28
        , 'loop':12
        , 'multiStateInput':13
        , 'multiStateOutput':14
        , 'multiStateValue':19
        , 'networkSecurity':38
        , 'notificationClass':15
        , 'octetstringValue':47
        , 'positiveIntegerValue':48
        , 'program':16
        , 'pulseConverter':24
        , 'schedule':17
        , 'structuredView':29
        , 'timePatternValue':49
        , 'timeValue':50
        , 'trendLog':20
        , 'trendLogMultiple':27
        }

expand_enumerations(ObjectType)

#
#   ObjectIdentifier
#

class ObjectIdentifier(Atomic):

    _app_tag = Tag.objectIdentifierAppTag
    objectTypeClass = ObjectType

    def __init__(self, *args):
        self.value = ('analog-input', 0)

        if len(args) == 0:
            pass
        elif len(args) == 1:
            arg = args[0]
            if isinstance(arg, Tag):
                self.decode(arg)
            elif isinstance(arg, types.IntType):
                self.set_long(long(arg))
            elif isinstance(arg, types.LongType):
                self.set_long(arg)
            elif isinstance(arg, types.TupleType):
                self.set_tuple(*arg)
            else:
                raise TypeError, "invalid constructor datatype"
        elif len(args) == 2:
            self.set_tuple(*args)
        elif isinstance(arg, ObjectIdentifier):
            self.value = arg.value
        else:
            raise ValueError, "invalid constructor parameters"

    def set_tuple(self, objType, objInstance):
        # allow a type name as well as an integer
        if isinstance(objType, types.IntType):
            # try and make it pretty
            objType = self.objectTypeClass._xlate_table.get(objType, objType)
        elif isinstance(objType, types.LongType):
            objType = self.objectTypeClass._xlate_table.get(objType, int(objType))
        elif isinstance(objType, types.StringType):
            # make sure the type is known
            if objType not in self.objectTypeClass._xlate_table:
                raise ValueError, "unrecognized object type '%s'" % (objType,)
        else:
            raise TypeError, "invalid datatype for objType: %r, %r" % (type(objType), objType)

        # pack the components together
        self.value = (objType, objInstance)

    def get_tuple(self):
        """Return the unsigned integer tuple of the identifier."""
        objType, objInstance = self.value

        if isinstance(objType, types.IntType):
            pass
        elif isinstance(objType, types.LongType):
            objType = int(objType)
        elif isinstance(objType, types.StringType):
            # turn it back into an integer
            objType = self.objectTypeClass()[objType]
        else:
            raise TypeError, "invalid datatype for objType"

        # pack the components together
        return (objType, objInstance)

    def set_long(self, value):
        # suck out the type
        objType = (value >> 22) & 0x03FF
        
        # try and make it pretty
        objType = self.objectTypeClass()[objType] or objType

        # suck out the instance
        objInstance = value & 0x003FFFFF

        # save the result
        self.value = (objType, objInstance)

    def get_long(self):
        """Return the unsigned integer representation of the identifier."""
        objType, objInstance = self.get_tuple()

        # pack the components together
        return long((objType << 22) + objInstance)

    def encode(self, tag):
        # encode the tag
        tag.set_app_data(Tag.objectIdentifierAppTag, struct.pack('>L',self.get_long()))

    def decode(self, tag):
        if (tag.tagClass != Tag.applicationTagClass) or (tag.tagNumber != Tag.objectIdentifierAppTag):
            raise ValueError, "object identifier application tag required"

        # extract the data
        self.set_long( struct.unpack('>L',tag.tagData)[0] )

    def __str__(self):
        # rip it apart
        objType, objInstance = self.value

        if isinstance(objType, types.StringType):
            typestr = objType
        elif objType < 0:
            typestr = "Bad %d" % (objType,)
        elif self.objectTypeClass._xlate_table.has_key(objType):
            typestr = self.objectTypeClass._xlate_table[objType]
        elif (objType < 128):
            typestr = "Reserved %d" % (objType,)
        else:
            typestr = "Vendor %d" % (objType,)
        return "ObjectIdentifier(%s,%d)" % (typestr, objInstance)

    def __hash__(self):
        return hash(self.value)

    def __cmp__(self, other):
        """Special function to make sure comparisons are done in enumeration
        order, not alphabetic order."""
        # hoop jump it
        if not isinstance(other, self.__class__):
            other = self.__class__(other)

        # get the numeric version
        a = self.get_long()
        b = other.get_long()

        # now compare the values
        if (a < b):
            return -1
        elif (a > b):
            return 1
        else:
            return 0

#
#   Application Tag Classes
#
#   This list is set in the Tag class so that the app_to_object
#   function can return one of the appliction datatypes.  It
#   can't be provided in the Tag class definition because the
#   classes aren't defined yet.
#

Tag._app_tag_class = \
    [ Null, Boolean, Unsigned, Integer
    , Real, Double, OctetString, CharacterString
    , BitString, Enumerated, Date, Time
    , ObjectIdentifier, None, None, None
    ]

