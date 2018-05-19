"""
responses.py

Python module used to classify and match responses from LCDd

Contains the following elements:
    - Enumeration listing out the responses possible from the daemon
    - Enumeration listing out attributes of responses from the daemon
    - Classifiers to distinguish the type of responses from strings
      sent from the daemon
    - Objects encapsulating each individual response
    - Factories and builders constructing response objects
      from each individual response

For information regarding LCDd terminology, please consult the LCDd developers'
documentation at the LCDproc website.

Copyright Shenghao Yang, 2018

See LICENSE.txt.txt for more details.
"""

import enum
import re
import typing

MAX_RESPONSE_LENGTH = 1000  # Maximum length of a response to even consider


class ResponseAttribute(enum.Flag):
    """
    Enumeration listing out the possible attributes that a response can have
    """
    SYNCHRONOUS = enum.auto()  # Message is a response to a client request
    ASYNCHRONOUS = enum.auto()  # Message is a status message from the daemon
    ERROR = enum.auto()  # Message is an error message


class ResponseType(enum.Enum):
    """
    Enumeration listing out all the possible responses from the
    daemon
    """
    SERVINFO = enum.auto()
    SUCCESS = enum.auto()
    ERROR = enum.auto()
    LISTEN = enum.auto()
    IGNORE = enum.auto()
    KEY = enum.auto()
    MENUEVENT = enum.auto()

    _attribute_map = {
        SERVINFO: ResponseAttribute.SYNCHRONOUS,
        SUCCESS: ResponseAttribute.SYNCHRONOUS,
        ERROR: (ResponseAttribute.SYNCHRONOUS | ResponseAttribute.ERROR),
        LISTEN: ResponseAttribute.ASYNCHRONOUS,
        IGNORE: ResponseAttribute.ASYNCHRONOUS,
        KEY: ResponseAttribute.ASYNCHRONOUS,
        MENUEVENT: ResponseAttribute.ASYNCHRONOUS,
    }

    _classifiers = {
        SERVINFO: lambda r: r.find('connect') == 0,
        SUCCESS: lambda r: r.find('success') == 0,
        ERROR: lambda r: r.find('huh') == 0,
        LISTEN: lambda r: r.find('listen') == 0,
        IGNORE: lambda r: r.find('ignore') == 0,
        KEY: lambda r: r.find('key') == 0,
        MENUEVENT: lambda r: r.find('menuevent') == 0,
    }

    @staticmethod
    def classify(response: str) -> typing.Union['ResponseType', None]:
        """
        Classify a response string as a particular response type

        :param response: response string form the daemon, which must include
                 the line ending character sequence
        :return: type of the response contained in the response string,
                 or ``None`` if the response string cannot be classified into
                 any particular type.
        .. warning::
            Responses longer than ``MAX_RESPONSE_LENGTH`` are also
            considered not to be classifiable as any particular type
        """
        for rtype, pred in ResponseType._classifiers.value.items():
            if pred(response) and (len(response) <= MAX_RESPONSE_LENGTH):
                # somehow, the dictionary converts the enumeration value
                # into the raw base value stored in the enumeration value
                # before using it as a dictionary key....
                # we have to convert the base value back into a value
                # that is of an enumeration type # todo INVESTIGATE
                return ResponseType(rtype)
        return None

    @staticmethod
    def attributes(rtype: 'ResponseType') -> ResponseAttribute:
        """
        Obtain the attributes for a particular type of response message

        :param rtype: type of response message from the daemon
        :return: set of flags that represent the attributes of a particular
                 response message.
        :raises: KeyError if the type of response message is invalid
        """
        return ResponseType._attribute_map.value[rtype]


class BaseResponse:
    """
    Base response class inherited by all response classes
    """

    def __init__(self, response: str):
        """
        Construct a response object representing a response from the lcd
        daemon

        :param response: response string from the lcd daemon, which must include
                         the line ending sequence.
        :raises ValueError: on invalid response string
        """
        rtype = ResponseType.classify(response)
        if rtype is None:
            raise ValueError(f'{self.__class__.__name__} '
                             f'constructed with response string of '
                             f'indeterminate type:'
                             f' {response}')
        else:
            self._response = response
            self._rtype = rtype

    @property
    def raw_response(self) -> str:
        """
        Obtain the raw response string from the lcd daemon

        :return: raw response string from the lcd daemon
        """
        return self._response

    @property
    def response_type(self) -> ResponseType:
        """
        Obtain the type of the response string as a member of an enumeration

        :return: type of the response string as an enumeration member
        """
        return self._rtype

    @property
    def response_attributes(self) -> ResponseAttribute:
        """
        Obtain the attributes associated with this particular response

        :return: attributes associated with this response
        """
        # see problem described in method classify of ResponseType
        return ResponseType.attributes(self._rtype.value)


class ServInfoResponse(BaseResponse):
    """
    Response class containing a server information response from the
    lcd daemon.
    """

    # regular expression used to match server information string
    _regex = re.compile('^connect LCDproc\s+'
                        '(?P<lcdproc_version>(\d+[.]?)*?((\d+)|[a-zA-Z]+))\s+'
                        'protocol'
                        '\s+(?P<protocol_version>(\d+[.]?)*?\d+)\s+'
                        'lcd\s+'
                        'wid\s+(?P<lcd_width>\d+)\s+'
                        'hgt\s+(?P<lcd_height>\d+)\s+'
                        'cellwid\s+(?P<character_width>\d+)\s+'
                        'cellhgt\s+(?P<character_height>\d+)')

    # no anchor at end because higher protocol versions may have
    # additional attributes

    def __init__(self, response: str):
        """
        Construct a new servinfo response object

        :param response: server information response string from the server,
                         containing the terminating newline sequence.
        :raises ValueError: on an invalid response string
        """
        super().__init__(response)
        if self.response_type is not ResponseType.SERVINFO:
            raise ValueError(f'{self.__class__.__name__} constructed with '
                             f'response of mismatching type: '
                             f'{self.response_type}')

        match = self._regex.match(response)
        if match is None:
            raise ValueError(f'{self.__class__.__name__} constructed with '
                             f'response of correct type but invalid'
                             f' content: {response}')
        else:
            self._lcdproc_version = match['lcdproc_version']
            self._protocol_version = match['protocol_version']
            self._lcd_width = int(match['lcd_width'])
            self._lcd_height = int(match['lcd_height'])
            self._character_width = int(match['character_width'])
            self._character_height = int(match['character_height'])

    @property
    def lcdproc_version(self) -> str:
        """
        Obtain the lcdproc version string encoded in the response message

        :return: lcdproc version string encoded in the response message, as a
                 sequence of dotted numbers.
        """
        return self._lcdproc_version

    @property
    def protocol_version(self) -> str:
        """
        Obtain the LCDd protocol version string encoded in the response
        message

        :return: LCDd protocol version string encoded in the response message,
                 as a sequence of dotted numbers.
        """
        return self._protocol_version

    @property
    def lcd_width(self) -> int:
        """
        Obtain the width of the LCD encoded in the response message

        :return: LCD width in character units.
        """
        return self._lcd_width

    @property
    def lcd_height(self) -> int:
        """
        Obtain the height of the LCD encoded in the response message

        :return: LCD height in character units
        """
        return self._lcd_height

    @property
    def character_width(self) -> int:
        """
        Obtain the width of a character (in pixels) on the LCD display.

        :return: character width in pixels.
        """
        return self._character_width

    @property
    def character_height(self) -> int:
        """
        Obtain the height of a character (in pixels) on the LCD display.

        :return: charcter height in pixels.
        """
        return self._character_height


class SuccessResponse(BaseResponse):
    """
    Response class containing a successful response from LCDd
    """

    # regular expression used to match success response string
    _regex = re.compile('^success$')

    def __init__(self, response: str):
        """
        Construct a new SuccessResponse instance

        :param response: response string from the server, containing the
                         line ending sequence.
        :raises ValueError: on invalid response string
        """
        super().__init__(response)
        if self.response_type is not ResponseType.SUCCESS:
            raise ValueError(f'{self.__class__.__name__} constructed with'
                             f' response of mismatching type: '
                             f'{self.response_type}')

        if self._regex.match(response) is None:
            raise ValueError(f'{self.__class__.__name__} constructed with'
                             f' response of correct type but invalid content: '
                             f'{response}')


class ErrorResponse(BaseResponse):
    """
    Response class containing an error response from LCDd
    """

    # regular expression used to match error response string
    _regex = re.compile('^huh[?]\s+(?P<reason>.*)$')

    def __init__(self, response: str):
        """
        Construct a new ErrorResponse instance

        :param response: response string from the server, containing the
                         line ending sequence
        :raises ValueError: on invalid response string
        """
        super().__init__(response)
        if self.response_type is not ResponseType.ERROR:
            raise ValueError(f'{self.__class__.__name__} constructed with'
                             f' response of mismatching type: '
                             f'{self.response_type}')

        match = self._regex.match(response)

        if match is None:
            raise ValueError(f'{self.__class__.__name__} constructed with'
                             f' response of correct type but invalid content: '
                             f'{response}')
        else:
            self._reason = match['reason']

    @property
    def reason(self) -> str:
        """
        Obtain the reason for the error message, encoded in the error
        response

        :return: error message reason
        """
        return self._reason


class ListenResponse(BaseResponse):
    """
    Response class containing a listen response from LCDd
    """

    # regular expression used to match listen response string
    _regex = re.compile('^listen\s+(?P<screen_id>\d+)$')

    def __init__(self, response: str):
        """
        Construct a new ListenResponse instance

        :param response: response string from the server, containing the line
                         ending sequence
        :raises ValueError: on invalid response string
        """
        super().__init__(response)
        if self.response_type is not ResponseType.LISTEN:
            raise ValueError(f'{self.__class__.__name__} constructed with'
                             f' response of mismatching type: '
                             f'{self.response_type}')

        match = self._regex.match(response)

        if match is None:
            raise ValueError(f'{self.__class__.__name__} constructed with'
                             f' response of correct type but invalid content: '
                             f'{response}')
        else:
            self._screen_id = int(match['screen_id'])

    @property
    def screen_id(self) -> int:
        """
        Obtain the ID of the screen that is encoded in this listen response

        :return: id of the screen encoded in this listen message
        """
        return self._screen_id


class IgnoreResponse(BaseResponse):
    """
    Response class containing a ignore response from LCDd
    """

    # regular expression used to match ignore response string
    _regex = re.compile('^ignore\s+(?P<screen_id>\d+)$')

    def __init__(self, response: str):
        """
        Construct a new IgnoreResponse instance

        :param response: response string from server, containing the line
                         ending sequence
        :raises ValueError: on invalid response string
        """
        super().__init__(response)
        if self.response_type is not ResponseType.IGNORE:
            raise ValueError(f'{self.__class__.__name__} constructed with'
                             f' response of mismatching type: '
                             f'{self.response_type}')

        match = self._regex.match(response)

        if match is None:
            raise ValueError(f'{self.__class__.__name__} constructed with'
                             f' response of correct type but invalid content: '
                             f'{response}')
        else:
            self._screen_id = int(match['screen_id'])

    @property
    def screen_id(self) -> int:
        """
        Obtain the ID of the screen that is encoded in this ignore response

        :return: id of the screen encoded in this ignore message
        """
        return self._screen_id


class KeyResponse(BaseResponse):
    """
    Response class containing a key response from LCDd

    .. warning::
        Currently unused and unimplemented. A stub implementation is present
        that doesn't do anything.

    todo IMPLEMENT
    """

    def __init__(self, response: str):
        """
        Construct a new KeyResponse instance

        :param response: response string from server, containing the line
                         ending sequence
        :raises ValueError: on invalid response string
        """
        super().__init__(response)


class MenuResponse(BaseResponse):
    """
    Response class containing a menu response from LCDd

    .. warning::
        Currently unused and unimplemented. A stub implementation is present
        that doesn't do anything.

    todo IMPLEMENT
    """

    def __init__(self, response: str):
        """
        Construct a new MenuResponse instance

        :param response: response string from server, containing the line
                         ending sequence
        :raises ValueError: on invalid response string
        """
        super().__init__(response)


_response_object_mapping = {
    ResponseType.SERVINFO: ServInfoResponse,
    ResponseType.SUCCESS: SuccessResponse,
    ResponseType.ERROR: ErrorResponse,
    ResponseType.LISTEN: ListenResponse,
    ResponseType.IGNORE: IgnoreResponse,
    ResponseType.KEY: KeyResponse,
    ResponseType.MENUEVENT: MenuResponse
}


def parse_response(response: str) -> BaseResponse:
    """
    Parse a response string that has been sent from LCDd

    A response string is a single line of response characters from LCDd, and not
    multiple replies from LCDd

    :param response: response string, containing the line ending sequence
    :return: response object matching the response string
    :raises ValueError: on invalid response string
    """
    rtype = ResponseType.classify(response)

    if rtype is None:
        raise ValueError('response string is of indeterminate type')
    else:
        return _response_object_mapping[rtype](response)
