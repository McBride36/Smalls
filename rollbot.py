#!/usr/bin/python
# -*- coding: latin-1 -*-
# import os, sys

# Import what's needed.
import random
import socket
import time
import json
import sys
import re
import requests
import arrow
from json_dict import JSONDict

mods = JSONDict("mods.json")

import praw
from logbook import Logger
commands = set()


def command(method):  # A decorator to automatically register and add commands to the bot.
    commands.add(method.__name__)
    return method


def owner_command(method):
    method.is_command = True

    def wrapper(self, hostmask, source, *args):
        if self.owner.lower() != source.lower():
            return "You can't control me {}!".format(source)
        return method(self, hostmask, source, *args)

    wrapper.is_command = True
    return wrapper


class RollBot:
    CONFIG_LOCATION = "./config.json"

    def __init__(self):
        self.command_list = {}
        self.logger = Logger('RollBot', level=2)
        self.logger.info("RollBot started.")
        self.last_ping = None
        self.registered = False

        with open(self.CONFIG_LOCATION) as f:
            self.config = json.load(f)
        self.nick = self.config['botnick']
        self.owner = self.config['owner']['nick']
        self.channels = set([x.lower() for x in self.config['channel']])
        self.command_prefix = self.config['prefix']

        self.command_list = {x: getattr(self, x) for x in commands}
        print("Added {} commands: {}".format(len(self.command_list), ", ".join(self.command_list.keys())))
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_file = self.socket.makefile(encoding="utf-8", errors="ignore")
        self.warn_interval = 5  # seconds
        self.last_warn = -self.warn_interval  # To allow using the warn command instantly.

    def send_message(self, channel, message):
        message_template = "PRIVMSG {} :{}"
        self.send_raw(message_template.format(channel, message))

    def send_ping(self, ping_message):
        message_template = "PONG : {}"
        self.send_raw(message_template.format(ping_message))
        self.update_ping_time()

    def join_channel(self, channel):
        if channel:
            message_template = "JOIN {}"
        self.send_raw(message_template.format(channel))

    def leave_channel(self, channel):
        if channel in self.channels:
            message_template = "PART {}"
            self.send_raw(message_template.format(channel))
            self.channels.remove(channel)

    def connect(self):
        server_information = (self.config['server'], self.config['port'])
        self.socket.connect(server_information)
        self.send_raw("PASS " + self.config['password'])
        self.send_raw("USER {} {} {} :{}".format(self.nick, self.nick, self.nick, "rollbot"))
        self.send_raw("NICK " + self.nick)
        self.run_loop()

    def get_message_from_server(self):
        return self.socket_file.readline()

    def run_loop(self):
        message_regex = r"^(?:[:](?P<prefix>\S+) )" \
                        r"?(?P<type>\S+)" \
                        r"(?: (?!:)(?P<destination>.+?))" \
                        r"?(?: [:](?P<message>.+))?$"  # Extracts all appropriate groups from a raw IRC message
        compiled_message = re.compile(message_regex)
        print(compiled_message)

        while True:
            try:
                message = self.get_message_from_server()
                self.logger.debug("Received server message: {}", message)
                parsed_message = compiled_message.finditer(message)
                message_dict = [m.groupdict() for m in parsed_message][0]  # Extract all the named groups into a dict
                source_nick = ""
                hostmask = ""
                ircmsg = message.strip('\n\r')  # remove new lines
                print(ircmsg.encode("ascii", errors="ignore"))

                if message_dict['prefix'] is not None:
                    if "!" in message_dict['prefix']:  # Is the prefix from a nickname?
                        hostmask = message_dict['prefix'].split("@")[1]
                        source_nick = message_dict['prefix'].split("!")[0]

                if message_dict['type'] == "PING":
                    self.send_ping(message_dict['message'])

                if message_dict['type'] == "PRIVMSG":
                    self.handle_message(hostmask, source_nick, message_dict['destination'], message_dict['message'])
                    # if source_nick not in mods:
                    #     mods[source_nick] = {"date":str(arrow.utcnow()), "message":message_dict['message'], "channel":message_dict['destination']}
                    if source_nick != "TagChatBot":
                        mods[source_nick] = {"date":str(arrow.utcnow()), "message":message_dict['message'], "channel":message_dict['destination']}

                if message_dict['type'] == "001":  # Registration confirmation message
                    self.registered = True
                    self.logger.info("{} connected to server successfully.", self.nick)
                    for channel in self.config['channel']:
                        self.logger.info("Attempting to join {}", channel)
                        self.join_channel(channel)

            except socket.timeout:
                self.logger.error("Disconnected. Attempting to reconnect.")
                self.socket.close()
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.connect()

    def handle_message(self, hostmask, source, destination, message):
        is_command = message.startswith(self.config['prefix'])
        if is_command:
            self.handle_command(hostmask, source, destination, message)

    def handle_command(self, hostmask, source, destination, message):
        try:
            split_message = message[1:].split()
            command_key = split_message[0].lower()
        except IndexError:
            self.logger.info("No Command")
            return
        arguments = split_message[1:]
        reply_to = destination
        try:
            if destination == self.nick:
                reply_to = source  # If it's a private message, reply to the source. Otherwise it's a channel message and reply there.
            if command_key in self.command_list:
                self.logger.info("Received command '{}' from {}", command_key, source)
                command = self.command_list[command_key]
                return_message = command(hostmask, source, reply_to, *arguments)
                if return_message is not None:
                    if isinstance(return_message, str):  # Is it a string?
                        self.send_message(reply_to, return_message)  # If so, just send it along.
                    else:  # Otherwise it's a list or a tuple
                        for message in return_message:  # So let's loop over them all
                            self.send_message(reply_to, message)  # And send them.
            else:
                pass
                # combined_command = self.command_prefix + command_key
                # self.send_message(reply_to, "Sorry, {} isn't a recognized command.".format(combined_command))
        except Exception as e:
            self.send_message(reply_to, "Sorry, I encountered an error while running that command.")
            print("Exception in command {}: {}".format(command_key, e))
    def send_raw(self, message):
        return self.socket.send((message + "\n").encode("utf-8"))

    def update_ping_time(self):
        self.last_ping = time.time()

    # Commands

    @command
    def commands(self, hostmask, source, reply_to, *args):
        return "Available commands: {}".format(", ".join(sorted(self.command_list.keys())))

    @command
    def netsplit(self, hostmask, source, reply_to, *args):
        return "technically we all netsplit http://pastebin.com/mPanErhR"

    @command
    def mods(self, hostmask, source, reply_to, *args):
        if reply_to != "#TPmods":
            if source in ["WOLOWOLO", "justanotheruser", "MRCOW", "LEBRONxJAMES", "defense_bot"]:
                return "can you not"
            else:
                return "Sorry! You must use this command in the channel #TPmods | Double click the channel to join."
        else:
            if ' '.join(args) == "":
                return "{} - Please recall !mods with a reason to notify a moderator.".format(source)
            else:
                self.send_raw("NAMES #TPmods")
                message = self.get_message_from_server()
                ircmsg = message.strip('\n\r')
                try:
                    actualip = "{}".format(re.findall(r'\b(?:\d{1,3}[\.-]){3}\d{1,3}\b', hostmask)[0])
                    actualipp = actualip.replace("-", ".")
                    ippfinal = " ( http://tagpro-origin.koalabeast.com/moderate/ips/{} )".format(actualipp)
                except IndexError:
                    ippfinal = ""
                if ircmsg.find(' 353 {} '.format(self.nick)) != -1:
                    namelist = ircmsg.split(":")[2]
                    modlist = " ".join(x[1:] for x in namelist.split() if x.startswith('+'))
                    oplist = " ".join(x[1:] for x in namelist.split() if x.startswith('@'))
                    modmsg = "- " + ' '.join(args)
                    if ' '.join(args) == "":
                        modmsg = ""
                    if modlist == "" and oplist == "":
                        self.send_raw(
                            "PRIVMSG #TPmods :Sorry {}, all mods are currently AFK. You can stick around or leave your request for one to find later.".format(
                                source))
                    else:
                        self.send_raw("PRIVMSG #TagProMods :Mods - {} {}".format(modlist, oplist))
                        self.send_raw(
                            "PRIVMSG #TPmods :{} - the mods have received your request. Please stay patient while waiting. Make sure to state the user/issue to speed up the request process.".format(
                                source))
                        self.send_raw(
                            "PRIVMSG #TagProMods :Mod request from {}{} in {} {}".format(source, ippfinal, reply_to,
                                                                                         modmsg))

    @command
    def check(self, hostmask, source, reply_to, *args):
        ipaddress = ' '.join(args)
        if re.match('^[-0-9.]*$', ipaddress):
            ipaddress = ipaddress.replace("-", ".")
        else:
            return "Sorry, that's not an IP address!"
        page = requests.get('http://check.getipintel.net/check.php?ip={}'.format(ipaddress))
        return "{}: chances of naughty IP = {}%".format(source, int(float(re.findall("(\d+(?:.\d+)?)", page.text)[0]) * 100))

    @command
    def seen(self, hostmask, source, replay_to, *args):
        name = ' '.join(args)
        if name not in mods:
            return "Sorry, haven't seen that weenie"
        if name in mods:
            timeseen = arrow.get(mods[name]["date"])
            formattime = timeseen.format(('YYYY-MM-DD HH:mm:ss ZZ'))
            humantime = timeseen.humanize()
            return "{} was seen {} ({}) saying {}".format(name,humantime, formattime, mods[name]["message"])


    @command
    def optin(self, hostmask, source, reply_to, *args):
        if reply_to not in ["#TagProMods","#tagprochat"]:
            return "Sorry! This command is not authorized here."
        if reply_to == "#TagProMods":
            self.send_raw("NAMES #TPmods")
            message = self.get_message_from_server()
            ircmsg = message.strip('\n\r')
            duty = "duty"
            if source == "Hootie":
                duty = "dootie"
            if source == "n00b":
                duty = "cutie"
            if ircmsg.find('+{}'.format(source)) != -1:
                return "You are already on {}, {}.".format(duty, source)
            elif ircmsg.find('{}'.format(source)) != -1:
                self.send_raw("PRIVMSG Chanserv :voice #TPmods {}".format(source))
                return "You are now on {}, {}.".format(duty, source)
            else:
                return "You are not in #TPmods, {}!".format(source)
        if reply_to == "#tagprochat":
            self.send_raw("NAMES #tagprochat")
            message = self.get_message_from_server()
            ircmsg = message.strip('\n\r')
            duty = "duty"
            if source == "Hootie":
                duty = "dootie"
            if source == "n00b":
                duty = "cutie"
            if ircmsg.find('+{}'.format(source)) != -1:
                return "You are already on {}, {}.".format(duty, source)
            elif ircmsg.find('{}'.format(source)) != -1:
                self.send_raw("PRIVMSG Chanserv :voice #tagprochat {}".format(source))
                return "You are now on {}, {}.".format(duty, source)
            else:
                return "You are not in #tagprochat, {}!".format(source)

    @command
    def optout(self, hostmask, source, reply_to, *args):
        if reply_to not in ["#TagProMods","#tagprochat"]:
            return "Sorry! This command is not authorized here."
        if reply_to == "#TagProMods":
            self.send_raw("NAMES #TPmods")
            message = self.get_message_from_server()
            ircmsg = message.strip('\n\r')
            duty = "duty"
            if source == "Hootie":
                duty = "dootie"
            if ircmsg.find('+{}'.format(source)) != -1:
                self.send_raw("PRIVMSG Chanserv :devoice #TPmods {}".format(source))
                if source.lower() in ['cignul9']:
                    return "Eat my ass {}".format(source)
                else: return "You are now off {}, {}.".format(duty, source)
            elif ircmsg.find('{}'.format(source)) != -1:
                return "You are already off {}, {}.".format(duty, source)
            else:
                return "You are not in #TPmods, {}!".format(source)
        if reply_to == "#tagprochat":
            self.send_raw("NAMES #tagprochat")
            message = self.get_message_from_server()
            ircmsg = message.strip('\n\r')
            duty = "duty"
            if source == "Hootie":
                duty = "dootie"
            if ircmsg.find('+{}'.format(source)) != -1:
                self.send_raw("PRIVMSG Chanserv :devoice #tagprochat {}".format(source))
                if source.lower() in ['cignul9']:
                    return "{} is a dink".format(source)
                else: return "You are now off {}, {}.".format(duty, source)
            elif ircmsg.find('{}'.format(source)) != -1:
                return "You are already off {}, {}.".format(duty, source)
            else:
                return "You are not in #tagprochat, {}!".format(source)

    @command
    def op(self, hostmask, source, reply_to, *args):
        if reply_to != "#TagProMods":
            return "Sorry! This command is not authorized here."
        else:
            self.send_raw("NAMES #TPmods")
            message = self.get_message_from_server()
            ircmsg = message.strip('\n\r')
            if ircmsg.find('@{}'.format(source)) != -1:
                return "You are already an operator, {}.".format(source)
            elif ircmsg.find('{}'.format(source)) != -1:
                self.send_raw("PRIVMSG Chanserv :op #TPmods {}".format(source))
                return "You are now an operator, {}.".format(source)
            else:
                return "You are not in #TPmods, {}!".format(source)

    @command
    def deop(self, hostmask, source, reply_to, *args):
        if reply_to != "#TagProMods":
            return "Sorry! This command is not authorized here."
        else:
            self.send_raw("NAMES #TPmods")
            message = self.get_message_from_server()
            ircmsg = message.strip('\n\r')
            if ircmsg.find('@{}'.format(source)) != -1:
                self.send_raw("PRIVMSG Chanserv :deop #TPmods {}".format(source))
                return "You are no longer an operator, {}.".format(source)
            elif ircmsg.find('{}'.format(source)) != -1:
                return "You are not an operator, {}.".format(source)
            else:
                return "You are not in #TPmods, {}!".format(source)

    @command
    def ticket(self, hostmask, source, reply_to, tickett=None, *args):
        if tickett is None:
            return "http://support.koalabeast.com/#/appeal"
        else:
            return "http://support.koalabeast.com/#/appeal/{}".format(tickett)

    @command
    def ip(self, hostmask, source, reply_to, *args):
        ipaddress = ' '.join(args)
        if re.match('^[-0-9.]*$', ipaddress):
            return ipaddress.replace("-", ".")
        else:
            return "Sorry, that's not an IP address!"

    @command
    def warn(self, hostmask, source, reply_to, *args):
        if reply_to != "#TagProMods":
            return "Sorry! This command is not authorized here."
        if time.time() - self.last_warn < self.warn_interval:
            return "You're using that too much."
        self.send_raw("NOTICE #TPmods :Please take off-topic discussion to #tagpro")
        self.last_warn = time.time()

    @owner_command
    def quit(self, hostmask, source, reply_to, *args):
        self.logger.warn("Shutting down by request of {}", source)
        self.send_raw("QUIT :{}'s out!".format(self.nick))
        self.socket.shutdown(1)
        self.socket.close()
        sys.exit()

    @owner_command
    def join(self, hostmask, source, reply_to, channel=None, *args):
        if channel is None:
            return "Please specify a channel you wish me to join."
        else:
            self.logger.info("Joining {} by request of {}".format(channel, source))
            self.join_channel(channel)

    @owner_command
    def part(self, hostmask, source, reply_to, channel=None, *args):
        if reply_to == source and channel is None:  # If this was a private message, we have no channel to leave.
            return "Sorry, you must run this command in a channel or provide a channel as an argument."
        elif channel is not None:
            if channel in self.channels:
                self.leave_channel(channel)
                return "Left channel {}!".format(channel)
            else:
                return "I don't believe I'm in that channel!"
        else:  # It was a channel message, so let's leave.
            self.leave_channel(reply_to)

    @owner_command
    def say(self, hostmask, source, reply_to, channel=None, *args):
        if reply_to != source:
            return "{} {}".format(channel, ' '.join(args))
        elif channel is not None:
            if channel in self.channels:
                self.send_message(channel, ' '.join(args))
            else:
                return "Whoops! I'm not in the channel {}".format(channel)
        else:
            return "The format is: |say <channel> <message>"


if __name__ == "__main__":
    bot = RollBot()
    bot.connect()
