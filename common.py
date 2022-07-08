"""	
	fe1dump
	Dumping Utility for Fire Emblem: Shadow Dragon and the Blade of Light (NES)
	Copyright 2022 Justin Olbrantz (Quantam)

	This work is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License. To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.
"""

import collections as colls
from ctypes import *
from enum import Enum, IntEnum, IntFlag, auto
import functools
import hashlib
import itertools
import re

namedtuple = colls.namedtuple

c_uint16_le = c_uint16.__ctype_le__
c_uint16_be = c_uint16.__ctype_be__

class iNesHeader(LittleEndianStructure):
	_pack_ = True
	_fields_ = (
		("sig", c_char * 4),
		("num_prg_16kbs", c_uint8),
		("num_chr_8kbs", c_uint8),
		("flags6", c_uint8),
		("flags7", c_uint8),
		("flags8", c_uint8),
		("flags9", c_uint8),
		# Don't care about the rest
	)

class Bitplane(Structure):
	_pack_ = True
	_fields_ = (("rows", c_uint8 * 8),)

class Tile(Structure):
	_pack_ = True
	_fields_ = (
		("low_plane", Bitplane),
		("high_plane", Bitplane),
	)

TileBank = Tile * 256

class ScriptOps(IntEnum):
	PlaySound = 0xdf
	ContinueMusic = 0xe0
	SetAutoInput = 0xe1
	DisablePortraitAnimation = 0xe2
	UpdateGoldDisplay = 0xe3
	RunScript = 0xe4
	DisplayMissionName = 0xe5
	RunScriptForOtherParticipant = 0xe6
	Interact = 0xe7
	DisplayPortrait = 0xe8
	SetDialogSpeed = 0xe9
	BeginParagraph = 0xea
	EndAndScrollLine = 0xeb
	InsertParameter = 0xec
	EndOfLine = 0xed
	PauseForInput = 0xee
	EndScript = 0xef

def leca4(banks, addr):
	bank_base = addr & 0xc000
	bank_idx = addr // 0x4000 - 2

	return addr - bank_base + banks[bank_idx] * 0x4000 + 0x10

def get_leca4(banks):
	return functools.partial(leca4, banks)

class TextDataBase:
	def __init__(self, rom, chr_start_offs):
		self._rom = rom
		self._chr_start_offs = chr_start_offs

		self._script_addrs = {}
		for bank_idx, set_lens in (
			(8, (0x33,)), 
			(12, (0x5e,)),
			(11, (0xb, 0x58)),  # There are 0x16 spots in the first table, but 0xb+ don't appear to point to valid data.
			):
			leca = get_leca4((bank_idx, 15))
			set_addrs = (c_uint16_le * len(set_lens)).from_buffer(rom, leca(0xbfe0))
			bank_sets = self._script_addrs[bank_idx] = []

			for set_idx, set_addr in enumerate(set_addrs):
				tbl_offs = leca(set_addr)
				bank_sets.append((c_uint16_le * set_lens[set_idx]).from_buffer(self._rom, tbl_offs))

		return

	def get_script_addrs(self):
		return self._script_addrs

	@classmethod
	def is_rom(cls, rom):
		for bank_idx, addr, size, hash_str in cls._check_seqs:
			offs = leca4((bank_idx, 15), addr)
			rom_hash = hashlib.sha256(rom[offs : offs + size]).digest()
			if hash_str and rom_hash != bytes.fromhex(hash_str):
				return False

		return True