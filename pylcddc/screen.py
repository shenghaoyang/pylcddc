"""
exceptions.py

Module containing classes to represent screens in LCDd

Contains the following classes:
    - ``Screen``: class used to represent a screen in LCDd
    - ``ScreenAttributeValues``: namespace containing
                                 various screen-attribute related enumerations

Copyright Shenghao Yang, 2018

See LICENSE.txt.txt for more details.
"""

import copy
import enum
import typing

from . import commands
from . import widgets


class ScreenAttributeValues:
    """
    Namespace containing enumerations that specify the non-trivial
    values provided as arguments to the command that allows setting of
    screen attributes.
    """

    class Priority(enum.Enum):
        """
        Enumeration listing all possible screen priorities that can be set
        as an value for the -priority argument
        """
        HIDDEN = 'hidden'
        BACKGROUND = 'background'
        INFO = 'info'
        FOREGROUND = 'foreground'
        ALERT = 'alert'
        INPUT = 'input'

    class Heartbeat(enum.Enum):
        """
        Enumeration listing all possible heartbeat settings that can be
        set as an value for the -hearbeat argument
        """
        ON = 'on'
        OFF = 'off'
        OPEN = 'open'

    class Backlight(enum.Enum):
        """
        Enumeration listing all possible backlight settings that can be
        set as an value for the -backlight argument
        """
        ON = 'on'
        OFF = 'off'
        TOGGLE = 'toggle'
        OPEN = 'open'
        BLINK = 'blink'
        FLASH = 'flash'

    class Cursor(enum.Enum):
        """
        Enumeration listing all possible cursor settings that can be
        set as an value for the -cursor argument
        """
        ON = 'on'
        OFF = 'off'
        UNDERLINE = 'under'
        BLOCK = 'block'


class Screen(widgets.WidgetContainer):
    """
    Class used to represent a screen in the LCDd world.

    The Screen class will manage widgets under its care, and is responsible for
    maintaining a collection of widgets that are displayed on this screen.

    The Screen class does not perform any sort of I/O, and only provides
    requests to the client class, which will setup / teardown / update
    screens appropriately, and handle all I/O errors.

    There is no ability to add / remove widgets from a screen,
    after constructing the screen.

    The Screen class is also designed to survive a transition from one
    client connection to another, just in case the client loses connection
    with LCDd..
    """

    def __init__(self, name: str, wids: typing.Iterable[widgets.Widget],
                 **attrs):
        """
        Create a new screen instance

        :param name: name of the screen instance - must be unique for a
                     particular screen
        :param wids: sequence of widgets to add to the screen
        :param attrs: attributes for the screen. Supported attributes are:
            - ``wid``: width of the screen, of type ``int``, >= 1
            - ``hgt``: height of the screen, of type ``int``, >= 1
            - ``priority``: priority of the screen, of type
                            ``commands.ScreenAttributes.Priority``
            - ``heartbeat``: heartbeat setting of the screen, of type
                             ``commands.ScreenAttributes.Heartbeat``
            - ``backlight``: backlight setting of the screen, of type
                             ``commands.ScreenAttributes.Backlight``
            - ``duration``: time the screen is visible, in eights
                            of seconds,
                            during each screen rotation cycle, of type
                            ``int``, >= 0
            - ``cursor``: cursor setting of the screen, of type
                          ``commands.ScreenAttributes.Cursor``
            - ``cursor_x``: x-coordinate of the cursor, of type ``int``, >= 1
            - ``cursor_y``: y-coordinate of the cursor, of type ``int``, >= 1
        Any attributes not set will assume their default values. For more
        information, see the LCDproc developer's manual.

        :raises ValueError: if the attributes are invalid
        :raises KeyError: if widgets have duplicate names. In this situation,
                          no widgets are added to the screen.
        :raises TypeError: if the attributes have invalid types
        """
        self.__class__.validate_attributes(attrs)
        self._attrs = attrs  # attributes of the screen
        self._attrs['name'] = name  # add name to attributes
        self._dict = dict()  # dictionary mapping widget name -> widget
        self._widget_ids = dict()  # dictionary mapping widget -> widget id
        self._widget_id_counter = 0  # widget ID counter, used to assign IDs

        for widget in wids:
            if widget.name in self:
                self._dict.clear()
                self._widget_id_counter = 0
                self._widget_ids.clear()
                raise ValueError(f'widget {widget} has a conflicts with '
                                 f'another widget with the same name. screen'
                                 f'creation aborted.')
            self._dict[widget.name] = widget
            self._widget_ids[widget.name] = tuple(
                range(self._widget_id_counter,
                      self._widget_id_counter + widget.ids_required, 1))
            self._widget_id_counter += widget.ids_required

    def __getitem__(self, name: str) -> widgets.Widget:
        return self._dict[name]

    def __len__(self) -> int:
        return len(self._dict)

    def __iter__(self) -> typing.Iterator[str]:
        return iter(self._dict)

    @staticmethod
    def validate_attributes(attrs):
        """
        Validate potential attributes of the screen.

        For information on supported attributes, see the constructor
        documentation for the ``Screen`` class.

        :param attrs: attributes to validate
        :raises ValueError: if the attributes are invalid
        :raises TypeError: if the attributes have invalid types
        """

        # no validators for other attributes are set, because
        # other attributes are all of integer type, so we only
        # need to validate if they are integers
        type_validators = {
            'priority': lambda p: isinstance(
                p, ScreenAttributeValues.Priority),
            'heartbeat': lambda h: isinstance(
                h, ScreenAttributeValues.Heartbeat),
            'backlight': lambda b: isinstance(
                b, ScreenAttributeValues.Backlight),
            'cursor': lambda c: isinstance(
                c, ScreenAttributeValues.Cursor)
        }

        # no need to validate values of enum attributes, because enum
        # attributes must be of their particular enum types, and if they
        # are the right type, then they cannot have the wrong value.
        value_validators = {
            'wid': lambda w: w >= 1,
            'hgt': lambda h: h >= 1,
            'cursor_x': lambda x: x >= 1,
            'cursor_y': lambda y: y >= 1,
            'duration': lambda d: d >= 0,
        }

        allowed_attributes = ('wid', 'hgt', 'priority', 'heartbeat',
                              'backlight', 'duration', 'cursor', 'cursor_x',
                              'cursor_y')

        for attr in attrs.keys():
            if attr not in allowed_attributes:
                raise ValueError('attempted to set attribute with invalid '
                                 f'name: {attr}')
        for attr, val in attrs.items():
            type_validator = type_validators.setdefault(
                attr, lambda v: isinstance(v, int))
            value_validator = value_validators.setdefault(
                attr, lambda v: True)
            if not type_validator(val):
                raise TypeError(f'wrong type for attribute: {attr},'
                                f' type: {type(val)}')
            if not value_validator(val):
                raise ValueError(f'wrong value for attribute: {attr},'
                                 f' value: {val}')

    @property
    def attrs(self) -> typing.Dict[str, typing.Any]:
        """
        Obtain a dictionary listing the attributes of the screen.

        The returned dictionary is a copy.
        Missing attributes assume their default values, as specified in
        the LCDproc developer's manual. The dictionary contains attributes
        stored as a mapping of strings to objects whose string representation
        can be directly sent to LCDd in a screen attribute set command
        without any further manipulation.

        :return: dictionary listing the attributes of the screen.
        """
        # shallow copy is enough because, for now, all attributes are immutable
        # may change in future, so do take note
        rtn = copy.copy(self._attrs)

        # Convert enumeration values into the strings they represent
        for attr, val in rtn.items():
            if isinstance(val, (ScreenAttributeValues.Priority,
                                ScreenAttributeValues.Cursor,
                                ScreenAttributeValues.Backlight,
                                ScreenAttributeValues.Heartbeat)):
                rtn[attr] = val.value
        return rtn

    @property
    def name(self) -> str:
        """
        Obtain the name of the screen

        :return: screen name
        """
        return self._attrs['name']

    def set_attrs(self, **attrs):
        """
        Set the attributes of the screen.

        :param attrs: attributes of the screen. See the constructor for the
                      Screen class regarding what attributes are supported.

        :raises ValueError: on invalid attribute value
        :raises TypeError: on invalid attribute type
        """
        self.validate_attributes(attrs)
        self._attrs.update(attrs)

    def update_attrs(self, screen_id: int) -> typing.Sequence[bytes]:
        """
        Obtain a request sequence that will update the attributes of the screen

        :param screen_id: id of the screen
        :return: request sequence
        """
        seq = list()
        seq.extend(commands.CommandGenerator.generate_set_screen_attrs_commands(
            screen_id, **self.attrs))
        return seq

    def init_all(self, screen_id: int) -> typing.Sequence[bytes]:
        """
        Obtain a sequence of bytes, with each bytes object representing a LCDd
        request, that will recreate the screen.

        This request sequence must add the screen, set the
        screen attributes, as well as add the widgets
        inside it, and update the states of the widgets in the screen
        to their states as defined in the widget objects.

        :param screen_id: id of the screen
        :return: request sequence
        """
        seq = list()
        seq.append(
            commands.CommandGenerator.generate_add_screen_command(screen_id))
        seq.extend(self.update_attrs(screen_id))
        for widget in self.values():
            seq.extend(widget.init_requests(screen_id,
                                            self._widget_ids[widget.name]))
        return seq

    def update_all(self, screen_id: int) -> typing.Sequence[bytes]:
        """
        Obtain a sequence of bytes, with each bytes object representing a
        LCDd request, that will update the state of the screen.

        The state update will update the attributes of the screen, as well
        as update the state of each of the widgets on the screen to match
        the states set in the objects representing them.

        :param screen_id: id of the screen
        :return: request sequence
        """
        seq = list()
        seq.extend(self.update_attrs(screen_id))
        for widget in self.values():
            seq.extend(widget.state_update_requests(
                screen_id, self._widget_ids[widget.name]))
        return seq

    def destroy_all_atomic(self, screen_id: int) -> bytes:
        """
        Obtain a sequence of bytes, forming a single request, that will
        destroy the screen.

        Currently, this returns the sequence of bytes forming a single
        ``del_screen`` command.

        :param screen_id: id of the screen
        :return: request byte sequence
        """
        return commands.CommandGenerator.generate_delete_screen_command(
            screen_id)
