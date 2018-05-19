# pylcddc

A python library for interfacing with ``LCDd``, the server
component of the commonly known ``LCDproc``

Features:

- Object-oriented interface support for all native 
  ``LCDd`` widgets
    - Full frame support, nest widget objects in frames, treat frames 
      like widget containers
- Decoupled thread to service ``LCDd`` screen switching responses 
- One I/O method to update screen, no funky exception handling everywhere

# More TODOs
- See ``TODO.md`` for more information and TODOs

# Version support
- Tested on ``LCDd`` packaged with ``LCDproc`` version ``0.5.9``
- Protocol version ``0.3``

# Modules for users
- ``pylcddc.client``: client for LCDd
- ``pylcddc.screen``: screens to attach to clients
- ``pylcddc.widgets``: widgets to place in screens
- ``pylcddc.exceptions``: exceptions raised by the library

# Modules for developers
- ``pylcddc.responses``: LCDd response decoder and abstractions
- ``pylcddc.commands``: LCDd request generation

# Examples
Don't really use these for production code...

See more examples in ``/demo``

## Simple usage for static display

```python
import pylcddc.client as client
import pylcddc.widgets as widgets
import pylcddc.screen as screen

title = widgets.Title('title_widget',
                      'Hello, World!')
main_scr = screen.Screen('main', [title])

c = client.Client('localhost', 13666)
c.add_screen(main_scr)
input('Press any key to exit')
c.close()
```

## Nest widgets in frames
```python
import pylcddc.client as client
import pylcddc.widgets as widgets
import pylcddc.screen as screen
import platform

flavorful_text_widgets = [widgets.String(f'flv_tx{i}', 1, 1 + i, text) for 
                          i, text in enumerate(
        'now you see me\nnow you dont\nso scary\nsuch wow'.splitlines())]
frame_top = widgets.Frame('frame_top', flavorful_text_widgets, 
                          1, 1, 10, 1, 10, 4, 
                          widgets.Frame.Direction.VERTICAL, 8)
platform_text = widgets.Scroller('platform', 1, 2, 20, 1,
                                 widgets.Scroller.Direction.HORIZONTAL, 1,
                                 'pylcddc running on ' 
                                 + ' '.join(platform.uname()))

main_scr = screen.Screen('main', [frame_top, platform_text])

c = client.Client('localhost', 13666)
c.add_screen(main_scr)
input('Press any key to exit')
c.close()
```

## Simple timed display updates and display attributes

```python
import pylcddc.client as client
import pylcddc.widgets as widgets
import pylcddc.screen as screen
import pylcddc.exceptions as lcdexcept
import time

time_string = widgets.Scroller('time', 1, 1, 20, 2,
                               widgets.Scroller.Direction.HORIZONTAL, 8,
                               time.ctime())
main_scr = screen.Screen('main', [time_string],
                         heartbeat=screen.ScreenAttributeValues.Heartbeat.OFF)

c = client.Client('localhost', 13666)
c.add_screen(main_scr)

print('pylcdd time demo\nUse ^C to exit')

try:
    while True:
        time_string.text = time.ctime()
        c.update_screen(main_scr)
        print('updated time to: ', time.ctime())
        time.sleep(0.1)
except lcdexcept.RequestError as e:
        print('LCDd refused our request', e)
except lcdexcept.FatalError as e:
        print('pylcddc fatal internal error', e)
except KeyboardInterrupt:
        print('exitting')

c.close()  # there might be exceptions from OS system call failures here
```

## Enable batched updates for faster operation *EXPERIMENTAL*
```python
import pylcddc.client as client
import pylcddc.widgets as widgets
import pylcddc.screen as screen
import pylcddc.exceptions as lcdexcept
import time

time_string = widgets.Scroller('time', 1, 1, 20, 2,
                               widgets.Scroller.Direction.HORIZONTAL, 8,
                               time.ctime())
main_scr = screen.Screen('main', [time_string],
                         heartbeat=screen.ScreenAttributeValues.Heartbeat.OFF)

c = client.Client('localhost', 13666)
c.add_screen(main_scr)

print('pylcdd time demo\nUse ^C to exit')

try:
    while True:
        time_string.text = time.ctime()
        c.update_screen(main_scr, True)
        print('updated time to: ', time.ctime())
        time.sleep(0.1)
except lcdexcept.RequestError as e:
        print('LCDd refused our request', e)
except lcdexcept.FatalError as e:
        print('pylcddc fatal internal error', e)
except KeyboardInterrupt:
        print('exitting')

c.close()  # there might be exceptions from OS system call failures here
```

# Licensing 
See ``LICENSE.txt`` for more details