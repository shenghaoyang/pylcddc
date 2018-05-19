import sys

import pylcddc.client as client
import pylcddc.exceptions as pylcddc_exceptions
import pylcddc.screen as screen
import pylcddc.widgets as widget


def main():
    c = client.Client(sys.argv[1], sys.argv[2])
    height = c.server_information_response.lcd_height
    width = c.server_information_response.lcd_width
    pixel_height = (height * c.server_information_response.character_height)
    pixel_width = (width * c.server_information_response.character_width)
    vbars = [widget.VerticalBar(f'vbar{i}', i, height, 0)
             for i in range(1, width + 1, 1)]
    hbars = [widget.HorizontalBar(f'hbar{i}', 1, i, 0)
             for i in range(1, height + 1, 1)]

    scr = screen.Screen(
        'vbar_screen', vbars,
        heartbeat=screen.ScreenAttributeValues.Heartbeat.OFF)
    scr2 = screen.Screen(
        'hbar_screen', hbars,
        heartbeat=screen.ScreenAttributeValues.Heartbeat.OFF)
    c.add_screen(scr)

    print('pylcddc bars demo - ctrl-c to exit')

    try:
        for bar in vbars:
            for i in range(pixel_height + 1):
                bar.length = i
                c.update_screen(scr, True)
        for bar in vbars:
            for i in range(pixel_height, -1, -1):
                bar.length = i
                c.update_screen(scr, True)
        c.delete_screen(scr)
        c.add_screen(scr2)
        for bar in hbars:
            for i in range(pixel_width + 1):
                bar.length = i
                c.update_screen(scr2, True)
        for bar in hbars:
            for i in range(pixel_width, -1, -1):
                bar.length = i
                c.update_screen(scr2, True)
    except pylcddc_exceptions.PylcddcError:
        print('pylcddc demo error. aborting!', file=sys.stderr)
    except KeyboardInterrupt:
        print('aborting due to user request')
    finally:
        c.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f'usage: {sys.argv[0]} host port')
    else:
        main()
    exit(0)
