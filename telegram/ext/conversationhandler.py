#!/usr/bin/env python
#
# A library that provides a Python interface to the Telegram Bot API
# Copyright (C) 2015-2016
# Leandro Toledo de Souza <devs@python-telegram-bot.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser Public License for more details.
#
# You should have received a copy of the GNU Lesser Public License
# along with this program.  If not, see [http://www.gnu.org/licenses/].
""" This module contains the ConversationHandler """

import logging

from telegram import Update
from telegram.ext import Handler
from telegram.utils.promise import Promise


class ConversationHandler(Handler):
    """
    A handler to hold a conversation with a user by managing three collections of other handlers.

    The first collection, a ``list`` named ``entry_points``, is used to initiate the conversation,
    for example with a ``CommandHandler`` or ``RegexHandler``.

    The second collection, a ``dict`` named ``states``, contains the different conversation steps
    and one or more associated handlers that should be used if the user sends a message when the
    conversation with them is currently in that state. You will probably use mostly
    ``MessageHandler`` and ``RegexHandler`` here.

    The third collection, a ``list`` named ``fallbacks``, is used if the user is currently in a
    conversation but the state has either no associated handler or the handler that is associated
    to the state is inappropriate for the update, for example if the update contains a command, but
    a regular text message is expected. You could use this for a ``/cancel`` command or to let the
    user know their message was not recognized.

    To change the state of conversation, the callback function of a handler must return the new
    state after responding to the user. If it does not return anything (returning ``None`` by
    default), the state will not change. To end the conversation, the callback function must
    return ``CallbackHandler.END`` or -1.

    Args:
        entry_points (list): A list of ``Handler`` objects that can trigger the start of the
            conversation.
        states (dict): A ``dict[object: list[Handler]]`` that defines the different states of
            conversation a user can be in and one or more associated ``Handler`` objects that
            should be used in that state. The first handler which ``check_update`` method returns
            ``True`` will be used.
        fallbacks (list): A list of handlers that might be used if the user is in a conversation,
            but every handler for their current state returned ``False`` on ``check_update``.
        allow_reentry (Optional[bool]): If set to ``True``, a user that is currently in a
            conversation can restart the conversation by triggering one of the entry points.
    """

    END = -1

    def __init__(self, entry_points, states, fallbacks, allow_reentry=False):
        self.entry_points = entry_points
        """:type: list[telegram.ext.Handler]"""
        self.states = states
        """:type: dict[str: telegram.ext.Handler]"""
        self.fallbacks = fallbacks
        """:type: list[telegram.ext.Handler]"""
        self.allow_reentry = allow_reentry

        self.conversations = dict()
        """:type: dict[(int, int): str]"""

        self.current_conversation = None
        self.current_handler = None

        self.logger = logging.getLogger(__name__)

    def check_update(self, update):

        if not isinstance(update, Update):
            return False

        user = None
        chat = None

        if update.message:
            user = update.message.from_user
            chat = update.message.chat

        elif update.edited_message:
            user = update.edited_message.from_user
            chat = update.edited_message.chat

        elif update.inline_query:
            user = update.inline_query.from_user

        elif update.chosen_inline_result:
            user = update.chosen_inline_result.from_user

        elif update.callback_query:
            user = update.callback_query.from_user
            chat = update.callback_query.message.chat if update.callback_query.message else None

        else:
            return False

        key = (chat.id, user.id) if chat else (None, user.id)
        state = self.conversations.get(key)

        if isinstance(state, Promise):
            self.logger.debug('waiting for promise...')
            state = state.result()

        self.logger.debug('selecting conversation %s with state %s' % (str(key), str(state)))

        handler = None

        # Search entry points for a match
        if state is None or self.allow_reentry:
            for entry_point in self.entry_points:
                if entry_point.check_update(update):
                    handler = entry_point
                    break

            else:
                if state is None:
                    return False

        # Get the handler list for current state, if we didn't find one yet and we're still here
        if state is not None and not handler:
            handlers = self.states.get(state)

            for candidate in (handlers or []):
                if candidate.check_update(update):
                    handler = candidate
                    break

            # Find a fallback handler if all other handlers fail
            else:
                for fallback in self.fallbacks:
                    if fallback.check_update(update):
                        handler = fallback
                        break

                else:
                    return False

        # Save the current user and the selected handler for handle_update
        self.current_conversation = key
        self.current_handler = handler

        return True

    def handle_update(self, update, dispatcher):

        new_state = self.current_handler.handle_update(update, dispatcher)

        if new_state == self.END:
            del self.conversations[self.current_conversation]
        elif new_state is not None:
            self.conversations[self.current_conversation] = new_state
