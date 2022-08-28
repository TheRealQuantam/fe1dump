"""	
	fe1dump
	Dumping Utility for Fire Emblem: Shadow Dragon and the Blade of Light (NES)
	Copyright 2022 Justin Olbrantz (Quantam)

	This work is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License. To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.
"""

import collections as colls
import collections.abc as cabc
from ctypes import *
from enum import Enum, IntEnum, IntFlag, auto
import functools
import hashlib
import itertools
import re

namedtuple = colls.namedtuple

c_uint16_le = c_uint16.__ctype_le__
c_uint16_be = c_uint16.__ctype_be__
c_int16_le = c_int16.__ctype_le__
c_int16_be = c_int16.__ctype_be__

num_terrains = 0x16
num_terrain_names = 0x10
num_metatiles = 0xd0
num_units = 0x16
num_ext_units = 0x18
num_pcs = 0x35
num_items = 0x5c
num_maps = 0x19

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

def load_term_lists(
	rom, 
	leca, 
	tbl_addr, 
	num_entries, 
	*, 
	ty = c_uint8, 
	terms = (0xef,), 
	end_offs = None,
	include_term = False,
):
	if not isinstance(terms, cabc.Sequence):
		terms = (terms,)
	tsize = sizeof(ty)
	add_len = int(bool(include_term)) if tsize == 1 else 0

	if len(terms) > 1:
		# TODO: Replace with RE
		def get_len(offs):
			sl = rom[offs:end_offs:tsize]
			lens = [sl.find(ch) for ch in terms]
			return min(filter(lambda x: x >= 0, lens))
	else:
		term = terms[0]
		get_len = lambda offs: rom[offs:end_offs:tsize].find(term)

	addrs = (c_uint16_le * num_entries).from_buffer(rom, leca(tbl_addr))
	lsts = []
	for addr in addrs:
		offs = leca(addr)
		length = get_len(offs) + add_len
		lsts.append((ty * length).from_buffer(rom, offs) if length else [])

	return addrs, lsts

def load_term_dicts(
	rom, 
	leca, 
	tbl_addr, 
	num_entries, 
	*, 
	ty = c_uint8, 
	terms = (0xef,), 
	end_offs = None,
	include_term = False,
	base_idx = 0,
):
	addrs, lsts = load_term_lists(rom, leca, tbl_addr, num_entries, ty = ty, terms = terms, end_offs = end_offs, include_term = include_term)
	dicts = {idx + base_idx: val for idx, val in enumerate(lsts)}

	return addrs, dicts

class TextDataBase:
	def __init__(
		self, 
		rom, 
		chr_start_offs,
		*args,
		script_params = None,
		terrain_name_params = None,
		unit_name_params = None,
		char_name_params = None,
		enemy_name_params = None,
		item_name_params = None,
		miss_name_params = None,
		loc_name_params = None,
		game_str_params = None,
		):
		self._rom = rom
		self._chr_start_offs = chr_start_offs

		if not script_params:
			script_params = (
				(3, (0x32,)),
				(4, (0x42, 0x36)),
				(7, (0, 0x6d)),
				(8, (0x33,)), 
				(12, (0x5e,)),
				(11, (0xb, 0x58)),  # There are 0x16 spots in the first table, but 0xb+ don't appear to point to valid data.
			)
		terrain_name_params = terrain_name_params or (0, 0xe5f1, num_terrain_names)
		unit_name_params = unit_name_params or (0, 0xda1f, num_ext_units)
		char_name_params = char_name_params or (0, 0xde2b, num_pcs)
		enemy_name_params = enemy_name_params or (0, 0xdfa4, 0x45)
		item_name_params = item_name_params or (0, 0xdad5, num_items)
		miss_name_params = miss_name_params  or (0, 0xee08, num_maps)
		loc_name_params = loc_name_params or (0, 0xefb7, num_maps)
		game_str_params = game_str_params or (11, 0x8fc2, 0x48)

		self._script_addrs = {}
		for bank_idx, set_lens in script_params:
			leca = get_leca4((bank_idx, 15))
			set_addrs = (c_uint16_le * len(set_lens)).from_buffer(rom, leca(0xbfe0))
			bank_sets = self._script_addrs[bank_idx] = []

			for set_idx, set_addr in enumerate(set_addrs):
				tbl_offs = leca(set_addr)
				bank_sets.append((c_uint16_le * set_lens[set_idx]).from_buffer(self._rom, tbl_offs))

		self._terrain_name_addrs, self.terrain_names = self._load_strings(*terrain_name_params)
		self._unit_name_addrs, self.unit_names = self._load_strings(*unit_name_params)
		self._char_name_addrs, self.char_names = self._load_strings(*char_name_params)
		self._enemy_name_addrs, self.enemy_names = self._load_strings(*enemy_name_params)
		self._item_name_addrs, self.item_names = self._load_strings(*item_name_params)
		self._miss_name_addrs, self.miss_names = self._load_strings(
			*miss_name_params, 
			(ScriptOps.EndOfLine,),
			False,
		)
		self._loc_name_addrs, self.loc_names = self._load_strings(
			*loc_name_params,
			(ScriptOps.EndOfLine,),
			False,
		)
		self._game_str_addrs, self.game_strs = self._load_strings(
			*game_str_params,
			(ScriptOps.EndOfLine, ScriptOps.EndScript),
		)

		return

	def _load_strings(self, bank_idx, tbl_addr, num_entries, terms = (ScriptOps.EndScript,), include_term = None):
		if include_term is None:
			include_term = terms != (ScriptOps.EndScript,)

		return load_term_lists(
			self._rom,
			get_leca4((bank_idx, 15)),
			tbl_addr,
			num_entries,
			ty = c_uint8,
			terms = terms,
			end_offs = self._chr_start_offs,
			include_term = include_term,
		)

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