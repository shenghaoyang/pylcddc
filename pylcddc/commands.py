"""
commands.py

Python module used to generate commands for LCDd

Contains the following elementss:
    - Enumeration listing containing all the possible commands that can be sent
      to LCDd
    - Enumeration listings for the non-trivial arguments to the commands
      that can be sent to LCDd
    - Functions that can be used to generate commands to be sent to LCDd

For information regarding LCDd terminology, please consult the LCDd developers'
documentation at the LCDproc website.

Copyright Shenghao Yang, 2018

See LICENSE.txt.txt for more details.

todo utf-8 or ASCII? should be equivalent and provide us with some future-proofing
"""

import enum
import typing

from .screen import ScreenAttributeValues
from .widgets import WidgetType


class Command(enum.Enum):
    """
    Enumeration listing all possible commands that can be sent to LCDd, 
    as well as the command headers for those commands.
    """
    INIT = 'hello'
    SET_CLIENT_ATTRS = 'client_set'
    ADD_SCREEN = 'screen_add'
    DELETE_SCREEN = 'screen_del'
    SET_SCREEN_ATTRS = 'screen_set'
    ADD_WIDGET = 'widget_add'
    DELETE_WIDGET = 'widget_del'
    SET_WIDGET_PARMS = 'widget_set'


class CommandGenerator:
    """
    Namespace containing functions utilized in generating commands to be sent
    to LCDd

    For functions that set attributes, no checking is made on the
    attribute names and the attribute values to ensure that they are valid.
    Callers are to check the validity of inputs from their own input sources.
    This is to avoid over-complicating the base layer because the
    set of valid attributes may change depending on the context.

    Quoting of values with embedded whitespace is performed automatically,
    as well as appropriate escaping of embedded double quotes in values.
    """

    @staticmethod
    def quote_string(string: str) -> str:
        """
        Enclose a string in double-quotes, as required by LCDd when a
        command argument to LCDd involves embedded whitespace.

        :param string: string enclose in double quotes
        :return: string enclosed in double quotes, with embedded double quotes
                 escaped with a backslash
        """
        escaped = string.replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def generate_attribute_setting(**attrs: typing.Dict[str, typing.Any]) \
            -> typing.Sequence[str]:
        """
        Generate a sequence of strings containing attributes and
        the values that the attrs
        are to be set to, meant for LCDd attribute set commands, in the form:

        -<attr0> <attr0_value>,
        -<attr1> <attr1_value>,
        ...
        -<attrn> <attrn_value>

        Before writing the value of an attribute to the setting string,
        the attribute is converted to its string representation using
        ``str()``

        :param attrs: attributes and the values they are to be set to
        :return: attribute setting string sequence
        """
        return [f'-{attr_name} '
                f'{CommandGenerator.quote_string(str(attr_value))}'
                for attr_name, attr_value in attrs.items()]

    @staticmethod
    def generate_init_command() -> bytes:
        """
        Generate a LCDd initialization command, to be sent before all other
        commands made by the client.

        :return: LCDd initialization command byte sequence that can be directly
                 sent to LCDd
        """
        return f'{Command.INIT.value}\n'.encode(encoding='utf-8')

    @staticmethod
    def generate_set_client_attrs_command(**attrs) -> typing.Sequence[bytes]:
        """
        Generate a sequence of LCDd commands to set client attributes

        :param attrs: client attributes to set
        :return: LCDd client attribute set command byte sequence that can
                 be directly sent to LCDd
        TODO FIXME
        """
        pass

    @staticmethod
    def generate_add_screen_command(screen_id: int) -> bytes:
        """
        Generate a LCDd command to add a screen

        :param screen_id: screen id of the screen
        :return: command byte sequence that can be directly sent to LCDd
        """
        return f'{Command.ADD_SCREEN.value} {screen_id}\n'.encode('utf-8')

    @staticmethod
    def generate_delete_screen_command(screen_id: int) -> bytes:
        """
        Generate a LCDd command to delete a screen

        :param screen_id: screen id of the screen
        :return: command byte sequence that can be directly sent to LCDd
        """
        return f'{Command.DELETE_SCREEN.value} {screen_id}\n'.encode('utf-8')

    @staticmethod
    def generate_set_screen_attrs_commands(screen_id: int, **attrs) \
            -> typing.Sequence[bytes]:
        """
        Generate a sequence of LCDd commands to set screen attributes

        Enumeration constants representing screen attributes
        are automatically converted to the raw values they represent.

        :param screen_id: id of the screen to set attributes for
        :param attrs: screen attributes to set
        :return: LCDd screen attribute set command byte sequences that can be
                 sent directly to LCDd
        """
        # convert the enum constants to the values of those
        # particular enumeration constants
        for attr, val in attrs.items():
            if isinstance(val, (ScreenAttributeValues.Priority,
                                ScreenAttributeValues.Cursor,
                                ScreenAttributeValues.Backlight,
                                ScreenAttributeValues.Heartbeat)):
                attrs[attr] = val.value

        attr_strings = CommandGenerator.generate_attribute_setting(**attrs)
        return [f'{Command.SET_SCREEN_ATTRS.value} {screen_id} '
                f'{attr_str}\n'.encode('utf-8')
                for attr_str in attr_strings]

    @staticmethod
    def generate_add_widget_command(screen_id: int, widget_id: int,
                                    wtype: WidgetType, frame_id=None) -> bytes:
        """
        Generate a LCDd command to add a widget to a screen

        :param screen_id: id of the screen to add the widget in
        :param widget_id: id to assign to the widget
        :param wtype: type of the widget
        :param frame_id: optional, id of the frame to add the widget to
        :return: LCDd widget add command byte sequence that can be sent
                 directly to LCDd
        """
        return (f'{Command.ADD_WIDGET.value} {screen_id} {widget_id} '
                f'{wtype.value}{" -in" if frame_id is not None else ""} '
                f'{frame_id if frame_id is not None else ""}\n').encode('utf-8')

    @staticmethod
    def generate_delete_widget_command(screen_id: int, widget_id: int) -> bytes:
        """
        Generate a LCDd command to delete a widget from a screen

        :param screen_id: id of the screen to remove the widget from
        :param widget_id: id of the widget to remove
        :return: LCDd widget remove command byte sequence that can be sent
                 directly to LCDd
        """
        return (f'{Command.DELETE_WIDGET.value} {screen_id} {widget_id}\n'
                ).encode('utf-8')

    @staticmethod
    def generate_set_widget_parms_command(screen_id: int, widget_id: int,
                                          *parms) -> bytes:
        """
        Generate a LCDd command to set widget parameters

        The parameters for the widget passed through this function will
        be converted to their string representations, then
        quoted and escaped, before their transmission to LCDd.

        :param screen_id: id of the screen containing the widget
        :param widget_id: id of the widget in the screen
        :param parms: parameters for the widget
        :return: LCDd widget parameter set command byte sequence that can
                 be sent directly to LCDd
        """
        output = [f'{Command.SET_WIDGET_PARMS.value} {screen_id} {widget_id}']
        for param in parms:
            output.append(CommandGenerator.quote_string(str(param)))
        output.append('\n')
        return ' '.join(output).encode('utf-8')
