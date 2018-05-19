"""
test_commands.py

Tests for the ``pylcddc.commands`` module, focusing on the
LCDd command generator.
"""

import unittest

import pylcddc.commands as commands


class TestCommandGenerator(unittest.TestCase):
    """
    Test the ability of the command generator to generate
    commands for LCDd.
    """

    def test_quote_string(self):
        """
        Test the ability of
        :meth:`commands.CommandGenerator.quote_string` to quote
        strings and escape embedded quotes
        """
        test_string = 'string_with_no_embedded_quotes'
        self.assertSequenceEqual(
            commands.CommandGenerator.quote_string(test_string),
            '"' + test_string + '"', 'quote_string() fails to quote', str)
        test_string = '"string_with_""_embedded"_quotes"'
        self.assertSequenceEqual(
            commands.CommandGenerator.quote_string(test_string),
            r'"\"string_with_\"\"_embedded\"_quotes\""',
            'quote_string() fails to escape and quote '
            'string with embedded quotes', str)

    def test_generate_attribute_setting(self):
        """
        Test the ability of
        :meth:`commands.CommandGenerator.generate_attribute_string`
        to generate strings from a dictionary containing attributes
        into a sequence of attribute strings in the form:

        ``-<attrn> "<attrn_value>"``

        Where ``attrn`` is the name of the attribute
        and ``attrn_value`` is the string-representation of the attribute,
        with double quotes inside escaped.

        Note that the ordering of attribute name-value pairs appearing in
        the attribute strings in the output sequence isn't
        guaranteed.
        """
        attrs = {
            'the': 1,
            'quick': 2,
            'brown': 3,
            'fox': 4,
            'jumps': 5,
            'over': '"string_with_""_embedded"_quotes"',
            'lazy': 'string_with_no_embedded_quotes'
        }
        reference = [f'-{attr} '
                     f'{commands.CommandGenerator.quote_string(attr_val)}'
                     for attr, attr_val in attrs.items()]
        self.assertSetEqual(
            set(reference),
            set(commands.CommandGenerator.generate_attribute_setting(
                **attrs)), 'generate_attribute_setting() failed to '
                           'generate correct attr-value strings')

    def test_generate_init_command(self):
        """
        Test the ability of
        :meth:`commands.CommandGenerator.generate_init_command`
        to generate a LCDd initialization command byte sequence
        """
        self.assertRegex(commands.CommandGenerator.generate_init_command(),
                         f'{commands.Command.INIT.value}[ ]*\n'.encode('utf-8'),
                         'generate_init_command() failed to generate'
                         'a LCDd initialization command')

    def test_generate_set_client_attrs_command(self):
        """
        Test the ability of
        :meth:`commands.CommandGenerator.generate_set_client_attrs_command`
        to generate a command sequence to set client attributes
        """
