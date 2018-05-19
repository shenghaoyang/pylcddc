"""
widgets.py

Python module modelling each individual LCDd widget as objects.

Contains the following elements:
    - Class hierarchy for widgets:
        - Classes modelling LCDd widgets
        - Base classes for widgets
        - Base classes for objects that contain other widgets

Copyright Shenghao Yang, 2018

See LICENSE.txt.txt for more details.

todo improve argument checking -> too much typing
"""

import abc
import collections
import enum
import string
import typing
from collections.abc import Mapping

from . import commands

# Characters accepted in free-form user text input by LCDd.
# According to the LCDd source, there are more characters accepted,
# such as control characters and the like, but we don't want to risk
# errors caused by sending invalid characters.
#
# Until there is a formal declaration of
# what characters are allowed, let's restrict ourselves to a
# safe subset of UTF-8.
ACCEPTABLE_CHARACTERS: str = (string.ascii_letters + string.punctuation
                              + string.digits + ' ')


class WidgetType(enum.Enum):
    """
    Enumeration listing all the possible widget types that the LCDd provides us,
    and provides the string representing the widget type that can be sent to
    LCDd when instantiating a widget.
    """
    STRING = 'string'
    TITLE = 'title'
    HORIZONTAL_BAR = 'hbar'
    VERTICAL_BAR = 'vbar'
    ICON = 'icon'
    SCROLLER = 'scroller'
    BIGNUM = 'num'
    FRAME = 'frame'


class Widget(abc.ABC):
    """
    Base class for all LCDd widgets

    LCDd widgets must be able to provide the following information to screens:
        - An initialization request sequence, that will setup the widget
        - An update request sequence, that will update the state of the widget
        - A teardown request sequence, that will destroy the widget

    Widgets are not bound to particular widget containers / screens,
    but widget containers maintain references to widgets, instead.

    ``__repr__()`` is not defined by this class because it has no idea
    of the arguments used to call into the constructor, for the derived
    subclasses, and we don't want to lead users astray. Derived classes
    should define it.
    """

    def __init__(self, wtype: WidgetType, name: str):
        """
        Initialize the widget base class

        :param wtype: type of widget
        :param name: name of widget, must be unique across all widgets
        """
        self._wtype = wtype
        self._name = name

    @abc.abstractmethod
    def __repr__(self) -> str:
        pass

    @property
    def ids_required(self) -> int:
        """
        Obtain the number of widget IDs needed by the widget to operate

        By default, the superclass implementation sets this to one.
        For more complex composite widgets, subclass implementors
        may override this property to increase the number of widget IDs
        requested from the screen

        :return: count of widget IDs
        """
        return 1

    @property
    def widget_type(self) -> WidgetType:
        """
        Obtain the type of the widget

        :return: widget type
        """
        return self._wtype

    @property
    def name(self) -> str:
        """
        Obtain the name of the widget

        :return: widget name
        """
        return self._name

    def init_requests(self, screen_id: int,
                      widget_ids: typing.Sequence[int],
                      frame_id: typing.Union[int, None] = None) \
            -> typing.Sequence[bytes]:
        """
        Obtain the sequence of requests, each represented with a bytes
        object, that will enable the screen to add the widget to itself
        and setup its state to match the state of the widget
        stored in the widget object.

        For widgets requiring only a single ID:
        The default implementation returns the ``widget_add`` request
        as well as all the requests from ``state_update_requests()``,
        so the widget can be added to the screen and have its state
        setup. Subclasses may modify this if they have special requirements.

        For widgets requiring more than a single ID:
        The implementation does not cater for that, and raises a
        ``NotImplementedError``

        :param screen_id: id of the screen the widget is attached to
        :param widget_ids: ids the widget was assigned by the screen
        :param frame_id: id of the frame that the widget is attached to,
                         can be ``None`` for no frame

        :return: request sequence
        """
        if self.ids_required == 1:
            requests = list()
            requests.append(
                commands.CommandGenerator.generate_add_widget_command(
                    screen_id, widget_ids[0], self.widget_type, frame_id))
            requests.extend(self.state_update_requests(screen_id, widget_ids))
            return requests
        else:
            raise NotImplementedError

    @abc.abstractmethod
    def state_update_requests(self, screen_id: int,
                              widget_ids: typing.Sequence[int]) \
            -> typing.Sequence[bytes]:
        """
        Obtain the sequence of requests, each represented with a
        bytes object, that will enable the screen to update the
        state of the object.

        :param screen_id: id of the screen the widget is attached to
        :param widget_ids: ids the widget was assigned by the screen

        :return: request sequence
        """
        raise NotImplementedError

    def destroy_requests(self, screen_id: int,
                         widget_ids: typing.Sequence[int]) \
            -> typing.Sequence[bytes]:
        """
        Obtain the sequence of requests, each represented with a
        bytes object, that will enable the screen to destroy the widget

        The default implementation returns the ``widget_del`` request,
        one for each widget id provided by the screen

        Subclasses may modify this if they have special requirements.

        :param screen_id: id of the screen the widget is attached to
        :param widget_ids: ids the widget was assigned by the screen

        :return: request sequence
        """
        requests = list()
        for wid in widget_ids:
            requests.append(
                commands.CommandGenerator.generate_delete_widget_command(
                    screen_id, wid))
        return requests


class WidgetContainer(Mapping, abc.ABC):
    """
    Base class for widget-containing classes
    """

    @abc.abstractmethod
    def __getitem__(self, name: str) -> Widget:
        """
        Obtain a widget from the container

        :param name: name of the widget
        :return: widget returned
        :raises KeyError: if no widget by that name is present
        """
        raise NotImplementedError

    @abc.abstractmethod
    def __len__(self) -> int:
        """
        Return the number of widgets in the container

        :return: number of widgets in the container
        """
        raise NotImplementedError

    @abc.abstractmethod
    def __iter__(self) -> typing.Iterator[str]:
        """
        Obtain an iterator iterating through the names of the widgets in the
        container

        :return: iterator iterating through the names of widgets in the
                container
        """
        raise NotImplementedError


class String(Widget):
    """
    Class representing a string widget in LCDd
    """

    def __init__(self, name: str, x: int, y: int, text: str):
        """
        Instantiate a string widget

        :param name: widget name
        :param x: x-coordinate to display the string at, starts from 1
        :param y: y-coordinate to display the string at, starts from 1
        :param text: text to display in the string. Only ASCII text
                     characters are allowed. See ``ACCEPTABLE_CHARACTERS``
                     for more information.
        :raises ValueError: on invalid arguments
        """
        super().__init__(WidgetType.STRING, name)
        self._validate_input(x, y, text)
        self._x = x
        self._y = y
        self._text = text

    def __repr__(self) -> str:
        return (f'{self.__class__.__name__}({self.name!r}, {self.x!r}, '
                f'{self.y!r}, {self.text!r})')

    def _validate_input(self, x: int, y: int, text: str):
        if (x < 1) or (y < 1):
            raise ValueError('invalid string placement coordinates'
                             f' x: {x} y: {y}')
        for ch in text:
            if ch not in ACCEPTABLE_CHARACTERS:
                raise ValueError(f'invalid character to display: {ch!r}')

    @property
    def x(self) -> int:
        """
        The x-coordinate where the text is displayed
        :return: x-coordinate of text start location
        :raises ValueError: when set to an invalid value
        """
        return self._x

    @x.setter
    def x(self, new_x: int):
        self._validate_input(new_x, self.y, self.text)
        self._x = new_x

    @property
    def y(self) -> int:
        """
        The y-coordinate where the text is displayed
        :return: y-coordinate of text start location
        :raises ValueError: when set to an invalid value
        """
        return self._y

    @y.setter
    def y(self, new_y: int):
        self._validate_input(self.x, new_y, self.text)
        self._y = new_y

    @property
    def text(self) -> str:
        """
        Text that is displayed
        :return: text displayed
        :raises ValueError: when set to an invalid value
        """
        return self._text

    @text.setter
    def text(self, new_text: str):
        self._validate_input(self.x, self.y, new_text)
        self._text = new_text

    def state_update_requests(self, screen_id: int,
                              widget_ids: typing.Sequence[int]) \
            -> typing.Sequence[bytes]:
        output = list()
        output.append(
            commands.CommandGenerator.generate_set_widget_parms_command(
                screen_id, widget_ids[0], self.x, self.y, self.text))
        return output


class Title(Widget):
    """
    Class representing a title widget in LCDd
    """

    def __init__(self, name: str, title: str):
        """
        Instantiate a title widget

        :param name: widget name
        :param title: text to display as the title. Only characters in
                      ``ACCEPTABLE_CHARACTERS`` are allowed.
        :raises ValueError: on invalid arguments
        """
        super().__init__(WidgetType.TITLE, name)
        self._validate_input(title)
        self._title = title

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.name!r}, {self.title!r})'

    def _validate_input(self, title: str):
        for ch in title:
            if ch not in ACCEPTABLE_CHARACTERS:
                raise ValueError(f'invalid character to display: {ch!r}')

    @property
    def title(self) -> str:
        """
        Access the title displayed by the title widget.

        :return: title displayed by the title widget
        :raises ValueError: on invalid title on set operation
        """
        return self._title

    @title.setter
    def title(self, new_title: str):
        self._validate_input(new_title)
        self._title = new_title

    def state_update_requests(self, screen_id: int,
                              widget_ids: typing.Sequence[int]) \
            -> typing.Sequence[bytes]:
        reqs = list()
        reqs.append(commands.CommandGenerator.generate_set_widget_parms_command(
            screen_id, widget_ids[0], self.title))
        return reqs


class Bar(Widget, abc.ABC):
    """
    Base class for bars in LCDd
    """

    def __init__(self, wtype: WidgetType,
                 name: str, x: int, y: int, length: int):
        """
        Instantiate a bar widget

        :param wtype: type of the widget, either a ``WidgetType.HORIZONTAL_BAR``
                      or a ``WidgetType.VERTICAL_BAR``
        :param name: name of the widget
        :param x: x-coordinate of the bar's starting position
        :param y: y-coordinate of the bar's starting position
        :param length: length of the bar in pixels
        :raises ValueError: on invalid arguments
        """
        if ((wtype is not WidgetType.HORIZONTAL_BAR)
                and (wtype is not WidgetType.VERTICAL_BAR)):
            raise ValueError(f'invalid bar type: {wtype}')
        super().__init__(wtype, name)
        self._validate_input(x, y, length)
        self._x = x
        self._y = y
        self._length = length

    def __repr__(self) -> str:
        return (f'{self.__class__.__name__}({self.x!r}, {self.y!r}, '
                f'{self.length!r})')

    def _validate_input(self, x: int, y: int, length: int):
        if (x < 1) or (y < 1):
            raise ValueError('invalid bar placement '
                             f'coordinates: x: {x}, y: {y}')
        if length < 0:
            raise ValueError('invalid bar length: {bar_length}')

    @property
    def x(self) -> int:
        """
        Access the x-coordinate of the bar's starting position

        :return: x-coordinate of starting position
        :raises ValueError: on setting the starting x-coordinate to an
                            invalid value
        """
        return self._x

    @x.setter
    def x(self, new_x: int):
        self._validate_input(new_x, self.y, self.length)
        self._x = new_x

    @property
    def y(self) -> int:
        """
        Access the y-coordinate of the bar's starting position

        :return: y-coordinate of the starting position
        :raises ValueError: on setting the starting y-coordinate
                            to an invalid value
        """
        return self._y

    @y.setter
    def y(self, new_y: int):
        self._validate_input(self.x, new_y, self.length)
        self._y = new_y

    @property
    def length(self) -> int:
        """
        Access the length of the bar

        :return: length of the bar, in pixels
        :raises ValueError: on setting the bar length to an invalid value
        """
        return self._length

    @length.setter
    def length(self, new_length: int):
        self._validate_input(self.x, self.y, new_length)
        self._length = new_length

    def state_update_requests(self, screen_id: int,
                              widget_ids: typing.Sequence[int]) \
            -> typing.Sequence[bytes]:
        reqs = list()
        reqs.append(commands.CommandGenerator.generate_set_widget_parms_command(
            screen_id, widget_ids[0], self.x, self.y, self.length))
        return reqs


class HorizontalBar(Bar):
    """
    Class representing a horizontal bar in LCDd
    """

    def __init__(self, name: str, x: int, y: int, length: int):
        """
        Instantiate a new horizontal bar widget.

        :param name: name of the widget
        :param x: x-coordinate of the bar's start position
        :param y: y-coordinate of the bar's start position
        :param length: length of the bar, in pixels
        :raises ValueError: on invalid arguments
        """
        super().__init__(WidgetType.HORIZONTAL_BAR, name, x, y, length)


class VerticalBar(Bar):
    """
    Class representing a vertical bar in LCDd
    """

    def __init__(self, name: str, x: int, y: int, length: int):
        """
        Instantiate a new vertical bar widget.

        :param name: name of the widget
        :param x: x-coordinate of the bar's start position
        :param y: y-coordinate of the bar's start position
        :param length: length of the bar, in pixels
        :raises ValueError: on invalid arguments
        """
        super().__init__(WidgetType.VERTICAL_BAR, name, x, y, length)


class Icon(Widget):
    """
    Class representing a LCDd icon
    """

    class IconType(enum.Enum):
        """
        Enumeration listing the different types of icons supported by
        LCDd.

        The names to specify when requesting for a particular icon to be
        displayed by LCDd, in a icon display command, are also
        included as the values of the particular enumeration
        constants.

        Allowed icons are sourced from LCDproc 0.5.9, ``server/widgets.c``
        """
        BLOCK_FILLED = 'BLOCK_FILLED'
        HEART_OPEN = 'HEART_OPEN'
        HEART_FILLED = 'HEART_FILLED'
        ARROW_UP = 'ARROW_UP'
        ARROW_DOWN = 'ARROW_DOWN'
        ARROW_LEFT = 'ARROW_LEFT'
        ARROW_RIGHT = 'ARROW_RIGHT'
        CHECKBOX_OFF = 'CHECKBOX_OFF'
        CHECKBOX_ON = 'CHECKBOX_ON'
        CHECKBOX_GRAY = 'CHECKBOX_GRAY'
        SELECTOR_AT_LEFT = 'SELECTOR_AT_LEFT'
        SELECTOR_AT_RIGHT = 'SELECTOR_AT_RIGHT'
        ELLIPSIS = 'ELLIPSIS'
        STOP = 'STOP'
        PAUSE = 'PAUSE'
        PLAY = 'PLAY'
        PLAYR = 'PLAYR'
        FF = 'FF'
        FR = 'FR'
        NEXT = 'NEXT'
        PREV = 'PREV'
        REC = 'REC'

    def __init__(self, name: str, x: int, y: int, icon: IconType):
        """
        Instantiate a new icon widget

        :param name: name of the widget
        :param x: x-coordinate to place the icon at
        :param y: y-coordinate to place the icon at
        :param icon: icon to display
        :raises ValueError on invalid arguments
        """
        super().__init__(WidgetType.ICON, name)
        self._x = x
        self._y = y
        self._icon = icon

    def __repr__(self) -> str:
        return (f'{self.__class__.__name__}({self.name!r}, {self.x!r}, '
                f'{self.y!r}, {self.icon!r})')

    def _validate_params(self, x: int, y: int):
        # icon is not validated because it is a value of enumeration type
        # so long as the type is correct, the value cannot be invalid,
        # unless the user did some trickery, in which case, ombwtfbbq, stop
        # h4x
        if (x < 1) or (y < 1):
            raise ValueError('invalid widget placement coordinates: '
                             f'x: {x}, y: {y}')

    @property
    def x(self) -> int:
        """
        Access the x-coordinate of the icon's placement position

        :return: x-coordinate of placement position
        :raises ValueError: when set to an invalid value
        """
        return self._x

    @x.setter
    def x(self, new_x: int):
        self._validate_params(new_x, self.y)
        self._x = new_x

    @property
    def y(self) -> int:
        """
        Access the y-coordinate of the icon's placement position

        :return: x-coordinate of placement position
        :raises ValueError: when set to an invalid value
        """
        return self._y

    @y.setter
    def y(self, new_y: int):
        self._validate_params(self.x, new_y)
        self._y = new_y

    @property
    def icon(self) -> IconType:
        """
        Acces the type of icon displayed

        :return: type of icon displayed
        """
        return self._icon

    @icon.setter
    def icon(self, new_icon: IconType):
        self._icon = new_icon

    def state_update_requests(self, screen_id: int,
                              widget_ids: typing.Sequence[int]) \
            -> typing.Sequence[bytes]:
        reqs = list()
        reqs.append(commands.CommandGenerator.generate_set_widget_parms_command(
            screen_id, widget_ids[0], self.x, self.y, self.icon.value))
        return reqs


class Scroller(Widget):
    """
    Class representing a scroller in LCDd
    """

    class Direction(enum.Enum):
        """
        Enumeration listing out all the possible scrolling
        directions for a scroller
        """
        HORIZONTAL = 'h'
        VERTICAL = 'v'
        MARQUEE = 'm'

    def __init__(self, name: str, x: int, y: int, width: int, height: int,
                 direction: Direction, speed: int, text: str):
        """
        Instantiate a new scroller widget

        :param name: name of the scroller widget
        :param x: x-coordinate of the scroller start position
        :param y: y-coordinate of the scroller start position
        :param width: width of the scroller widget
        :param height: height of the scroller widget
        :param direction: direction to scroll in
        :param speed: speed of scrolling, which is the
                      number of rendering slices (of which there are eight
                      in a second, by default) per unit movement of the
                      scroller.
        :param text: text to display. Only characters in
                     ``ACCEPTABLE_CHARACTERS`` are allowed.
        :raises ValueError: on invalid arguments
        """
        super().__init__(WidgetType.SCROLLER, name)
        self._validate_input(x, y, width, height, speed, text)
        self._x = x
        self._y = y
        self._width = width
        self._height = height
        self._direction = direction
        self._speed = speed
        self._text = text

    def _validate_input(self, x: int, y: int, width: int, height: int,
                        speed: int, text: str):
        if (x < 1) or (y < 1):
            raise ValueError('invalid placement coordinates:'
                             ' x: {x}, y: {y}')
        if (width < 1) or (height < 1):
            raise ValueError('invalid dimensions: width: {width}'
                             ' height: {height}')
        if speed < 0:
            raise ValueError('invalid speed: {speed}')
        for ch in text:
            if ch not in ACCEPTABLE_CHARACTERS:
                raise ValueError(f'invalid character in text: {ch!r}')

    def __repr__(self):
        return (f'{self.__class__.__name__}({self.name!r}, {self.x!r}, '
                f'{self.y!r}, {self.width!r}, {self.height!r}, '
                f'{self.direction!r}, {self.speed!r}, {self.text!r})')

    @property
    def x(self) -> int:
        """
        Access the x-coordinate of the scroller's starting position

        :return: scroller start x-coordinate
        :raises ValueError: if set to an invalid value
        """
        return self._x

    @x.setter
    def x(self, new_x: int):
        self._validate_input(new_x, self.y, self.width, self.height, self.speed,
                             self.text)
        self._x = new_x

    @property
    def y(self) -> int:
        """
        Access the y-coordinate of the scroller's starting position

        :return: scroller start y-coordinate
        :raises ValueError: if set to an invalid value
        """
        return self._y

    @y.setter
    def y(self, new_y: int):
        self._validate_input(self.x, new_y, self.width, self.height, self.speed,
                             self.text)
        self._y = new_y

    @property
    def width(self) -> int:
        """
        Access the width of the scroller

        :return: width of the scroller
        :raises ValueError: if set to an invalid value
        """
        return self._width

    @width.setter
    def width(self, new_width: int):
        self._validate_input(self.x, self.y, new_width, self.height, self.speed,
                             self.text)
        self._width = new_width

    @property
    def height(self) -> int:
        """
        Access the height of the scroller

        :return: height of the scroller
        :raises ValueError: if set to an invalid value
        """
        return self._height

    @height.setter
    def height(self, new_height: int):
        self._validate_input(self.x, self.y, self.width, new_height, self.speed,
                             self.text)
        self._height = new_height

    @property
    def direction(self) -> Direction:
        """
        Access the direction of the scroller

        :return: direction of the scroller
        :raises ValueError: if set to an invalid value
        """
        return self._direction

    @direction.setter
    def direction(self, new_direction: Direction):
        # no value checking needed - type is assured, unless user got the
        # type wrong, which shouldn't be the case for a type-annotated value.
        self._direction = new_direction

    @property
    def speed(self) -> int:
        """
        Access the speed of the scroller

        :return: speed of the scroller
        :raises ValueError: if set to an invalid value
        """
        return self._speed

    @speed.setter
    def speed(self, new_speed: int):
        self._validate_input(self.x, self.y, self.width, self.height, new_speed,
                             self.text)
        self._speed = new_speed

    @property
    def text(self) -> str:
        """
        Access the text scrolled by the scroller

        :return: text scrolled by the scroller
        :raises ValueError: if set to an invalid value
        """
        return self._text

    @text.setter
    def text(self, new_text: str):
        self._validate_input(self.x, self.y, self.width, self.height,
                             self.speed, new_text)
        self._text = new_text

    def state_update_requests(self, screen_id: int, widget_ids: typing.Sequence[int]) \
            -> typing.Sequence[bytes]:
        reqs = list()
        reqs.append(commands.CommandGenerator.generate_set_widget_parms_command(
            screen_id, widget_ids[0], self.x, self.y,
            self.x + self.width - 1,
            self.y + self.height - 1,
            self.direction.value,
            self.speed,
            self.text))
        return reqs


class Frame(Widget, WidgetContainer):
    """
    Class representing a frame widget in LCDd
    """

    class Direction(enum.Enum):
        """
        Enumeration listing all the possible directions a
        frame can scroll in
        """
        HORIZONTAL = 'h'
        VERTICAL = 'v'

    def __init__(self, name: str,
                 wids: typing.Iterable[Widget],
                 x: int, y: int, width: int, height: int,
                 inner_width: int, inner_height: int,
                 direction: Direction, speed: int):
        """
        Construct a new frame widget

        :param name: name of the frame widget
        :param wids: widgets to enclose in the frame
        :param x: x-coordinate of the top-left corner of the frame
        :param y: y-coordinate of the top-right corner of the frame
        :param width: width of the frame displayed on the screen the frame
                      is attached to
        :param height: height of the frame displayed on the screen
                       the frame is attached to
        :param inner_width: width of the virtual screen contained inside
                            the frame
        :param inner_height: height of the virtual
                             screen contained inside the frame
        :param direction: direction the frame should scroll in
        :param speed: speed of scrolling of the frame, specified as the
                      number of rendering ticks it takes for one
                      unit of scrolling movement. By default, LCDd
                      instances have 8 render ticks per second, and, so,
                      a speed of 8 will have the frame take 1 second to
                      scroll one unit.
        :raises KeyError: on widgets with duplicate names
        :raises ValueError: on invalid arguments

        """
        super().__init__(WidgetType.FRAME, name)
        self._validate_params(x, y, width, height, inner_width, inner_height,
                              speed)

        self._x = x
        self._y = y
        self._width = width
        self._height = height
        self._inner_width = inner_width
        self._inner_height = inner_height
        self._direction = direction
        self._speed = speed

        # the underlying mapping container must be ordered,
        # in order to maintain consistency of widget ids used
        # for widgets
        self._widgets = collections.OrderedDict()
        for widget in wids:
            if widget.name in self:
                raise KeyError('widget has name collision with '
                               f'another stored widget: {widget.name}')
            self._widgets[widget.name] = widget

    def __repr__(self) -> str:
        return (f'{self.__class__.__name__}({self.name!r}, '
                f'({", ".join([repr(widget) for widget in self.values()])}), '
                f'{self.x!r}, {self.y!r}, {self.width!r}, {self.height!r}, '
                f'{self.inner_width!r}, {self.inner_height!r}, '
                f'{self.direction!r}, {self.speed!r})')

    def __getitem__(self, name: str) -> Widget:
        return self._widgets[name]

    def __len__(self) -> int:
        return len(self._widgets)

    def __iter__(self) -> typing.Iterator[str]:
        return iter(self._widgets)

    def _validate_params(self, x: int, y: int, width: int,
                         height: int, inner_width: int,
                         inner_height: int, speed: int):
        # direction is not validated because it is guaranteed to be a
        # valid value unless the user is a h4x0r
        if (x < 1) or (y < 1):
            raise ValueError('invalid widget placement coordinates:'
                             f' x: {x}, y: {y}')
        if (width < 1) or (height < 1):
            raise ValueError('invalid widget dimensions: '
                             f'width: {width}, height: {height}')
        if (inner_width < 1) or (inner_height < 1):
            raise ValueError('invalid frame virtual screen dimensions: '
                             f'width: {inner_width}, height: {inner_height}')
        if speed < 0:
            raise ValueError(f'invalid speed: {speed}')

    @property
    def ids_required(self) -> int:
        # generate the amount of ids required for the frame according to the
        # number of ids required, which lets us support nested frames.....
        # composite widgets, etc.
        # not sure if lcdd does have that support...
        return sum((widget.ids_required for widget in self.values())) + 1

    @property
    def x(self) -> int:
        """
        Access the x-coordinate of the frame's placement position

        :return: x-coordinate of the frame's placement position
        :raises ValueError: when set to an invalid value
        """
        return self._x

    @x.setter
    def x(self, new_x: int):
        self._validate_params(new_x, self.y, self.width, self.height,
                              self.inner_width, self.inner_height, self.speed)
        self._x = new_x

    @property
    def y(self) -> int:
        """
        Access the y-coordinate of the frame's placement position

        :return: y-coordinate of the frame's placement position
        :raises ValueError: when set to an invalid value
        """
        return self._y

    @y.setter
    def y(self, new_y: int):
        self._validate_params(self.x, new_y, self.width, self.height,
                              self.inner_width, self.inner_height, self.speed)
        self._y = new_y

    @property
    def width(self) -> int:
        """
        Access the width of the frame

        :return: frame width
        :raises ValueError: when set to an invalid value
        """
        return self._width

    @width.setter
    def width(self, new_width: int):
        self._validate_params(self.x, self.y, new_width, self.height,
                              self.inner_width, self.inner_height, self.speed)
        self._width = new_width

    @property
    def height(self) -> int:
        """
        Access the height of the frame

        :return: frame height
        :raises ValueError: when set to an invalid value
        """
        return self._height

    @height.setter
    def height(self, new_height: int):
        self._validate_params(self.x, self.y, self.width, new_height,
                              self.inner_width, self.inner_height, self.speed)
        self._height = new_height

    @property
    def inner_width(self) -> int:
        """
        Access the width of the inner virtual screen contained in the
        frame

        :return: virtual frame width
        :raises ValueError when set to an invalid width
        """
        return self._inner_width

    @inner_width.setter
    def inner_width(self, new_width: int):
        self._validate_params(self.x, self.y, self.width, self.height,
                              new_width, self.inner_height, self.speed)
        self._inner_width = new_width

    @property
    def inner_height(self) -> int:
        """
        Access the height of the inner virtual screen contained in the
        frame

        :return: virtual frame height
        :raises ValueError when set to an invalid height
        """
        return self._inner_height

    @inner_height.setter
    def inner_height(self, new_height: int):
        self._validate_params(self.x, self.y, self.width, self.height,
                              self.inner_width, new_height, self.speed)
        self._inner_height = new_height

    @property
    def direction(self) -> Direction:
        """
        Access the scrolling direction of the frame

        :return: frame scrolling direction
        """
        return self._direction

    @direction.setter
    def direction(self, new_direction: Direction):
        self._direction = new_direction

    @property
    def speed(self) -> int:
        """
        Access the scrolling speed of the frame, in units of
        rendering ticks per unit scrolling movement

        :return: scrolling speed
        :raises ValueError: when set to an invalid value
        """
        return self._speed

    @speed.setter
    def speed(self, new_speed: int):
        self._validate_params(self.x, self.y, self.width, self.height,
                              self.inner_width, self.inner_height, new_speed)
        self._speed = new_speed

    def init_requests(self, screen_id: int, widget_ids: typing.Sequence[int],
                      frame_id: typing.Union[int, None] = None) \
            -> typing.Sequence[bytes]:
        # overridden here because we have to initialize lots of other
        # widgets as well
        # append initialization sequence for frame
        reqs = list()
        frame_widget_id = widget_ids[0]
        reqs.append(commands.CommandGenerator.generate_add_widget_command(
            screen_id, frame_widget_id, self.widget_type))

        # append sequence for other widgets
        allowed_ids = widget_ids[1:]
        for widget in self.values():
            # this is why an ordereddict is needed, because we *don't* store
            # the widget IDs, and we must always iterate through them in a
            # consistent order so we always address the widgets using
            # the same ID sets, i.e. the first i.d. set given by the screen
            # is always used for the frame, the second i.d. set given by the
            # frame is always used for the first widget, and so on so forth
            reqs.extend(widget.init_requests(
                screen_id, allowed_ids[:widget.ids_required], frame_widget_id))
            allowed_ids = allowed_ids[widget.ids_required:]

        # append configuration sequence for frame and widgets
        reqs.extend(self.state_update_requests(screen_id, widget_ids))

        return reqs

    def state_update_requests(self, screen_id: int,
                              widget_ids: typing.Sequence[int]) \
            -> typing.Sequence[bytes]:
        # append configuration sequence for frame
        reqs = list()
        frame_widget_id = widget_ids[0]
        reqs.append(commands.CommandGenerator.generate_set_widget_parms_command(
            screen_id, frame_widget_id, self.x, self.y,
            self.x + self.width - 1,
            self.y + self.height - 1,
            self.inner_width,
            self.inner_height,
            self.direction.value,
            self.speed
        ))

        # append configuration sequence for widgets
        allowed_ids = widget_ids[1:]
        for widget in self.values():
            # this is why an ordereddict is needed, because we *don't* store
            # the widget IDs, and we must always iterate through them in a
            # consistent order so we always address the widgets using
            # the same ID sets, i.e. the first i.d. set given by the screen
            # is always used for the frame, the second i.d. set given by the
            # frame is always used for the first widget, and so on so forth
            reqs.extend(widget.state_update_requests(
                screen_id, allowed_ids[:widget.ids_required]))
            allowed_ids = allowed_ids[widget.ids_required:]

        return reqs


class Num(Widget):
    """
    Widget representing a big decimal digit
    """

    class SpecialDigit(enum.Enum):
        COLON = 10

    def __init__(self, name: str, x: int,
                 digit: typing.Union[int, SpecialDigit]):
        """
        Instantiate a new bignum widget

        Bignums are large decimal digits 3 characters wide and 4 characters
        tall

        :param name: name of the widget
        :param x: x-coordinate to display the digit at
        :param digit: digit to display, or an equivalent special digit to
                      display.
        :raises: ValueError: on invalid arguments
        """
        super().__init__(WidgetType.BIGNUM, name)
        self._validate_params(x, digit)

        self._x = x
        self._digit = digit

    def __repr__(self) -> str:
        return (f'{self.__class__.__name__}({self.name!r}, {self.x!r}, '
                f'{self.digit!r})')

    def _validate_params(self, x: int, digit: typing.Union[int, SpecialDigit]):
        if x < 1:
            raise ValueError(f'invalid bignum placement position: x: {x}')
        if isinstance(digit, int):
            if digit not in range(10):
                raise ValueError(f'invalid decimal digit to display: {digit}')

    @property
    def x(self) -> int:
        """
        Access the coordinate this big decimal digit is displayed at.

        :return: coordinate this digit is displayed at
        :raises ValueError: when set to an invalid value
        """
        return self._x

    @x.setter
    def x(self, new_x: int):
        self._validate_params(new_x, self.digit)
        self._x = new_x

    @property
    def digit(self) -> typing.Union[int, SpecialDigit]:
        """
        Access the digit / special digit displayed

        :return: digit / special digit displayed
        :raises ValueError: when set to an invalid value
        """
        return self._digit

    @digit.setter
    def digit(self, new_digit: typing.Union[int, SpecialDigit]):
        self._validate_params(self.x, new_digit)
        self._digit = new_digit

    def state_update_requests(self, screen_id: int,
                              widget_ids: typing.Sequence[int]) \
            -> typing.Sequence[bytes]:
        reqs = list()
        reqs.append(commands.CommandGenerator.generate_set_widget_parms_command(
            screen_id, widget_ids[0], self.x,
            self.digit if isinstance(self.digit, int) else self.digit.value
        ))
        return reqs
