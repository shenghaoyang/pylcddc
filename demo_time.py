"""
demo_time.py

pylcddc demonstration module.

Displays the time, as formatted by ``time.ctime()``, on to the first row of
the display, scrolling vertically to show the full time string.

Accepts two command line arguments, the first being the host to connect to
and the second being the port to connect to.

Run this module by calling ``python demo_time.py <host> <port>``

Copyright Shenghao Yang, 2018

See LICENSE.txt for more details.
"""
import sys
import time

import pylcddc.client as client
import pylcddc.exceptions as pylcddc_exceptions
import pylcddc.screen as screen
import pylcddc.widgets as widget


def main():
    c = None
    try:
        c = client.Client(sys.argv[1], sys.argv[2])
        width, height = (c.server_information_response.lcd_width,
                         c.server_information_response.lcd_height)
        ctime = widget.Scroller('ctime', 1, 1, width, 1,
                                widget.Scroller.Direction.VERTICAL, 8,
                                time.ctime())
        scr = screen.Screen('ctime_screen', (ctime,),
                            heartbeat=screen.ScreenAttributeValues.Heartbeat.OFF)
        c.add_screen(scr)

        print('pylcddc time demo - ctrl-c to exit')

        while True:
            ctime.text = time.ctime()
            c.update_screens([scr], True)
    except pylcddc_exceptions.PylcddcError:
        print('pylcddc demo error. aborting!', file=sys.stderr)
    except KeyboardInterrupt:
        print('aborting due to user request')
    finally:
        if c is not None:
            c.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f'usage: {sys.argv[0]} host port')
    else:
        main()
    exit(0)
