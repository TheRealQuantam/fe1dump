"""	
	fe1dump
	Dumping Utility for Fire Emblem: Shadow Dragon and the Blade of Light (NES)
	Copyright 2022 Justin Olbrantz (Quantam)

	This work is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License. To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.
"""

import numpy as np
import numpy.ma as ma

from common import *
import text_original
import text_polinym

_nes_pal_str = """ 84  84  84    0  30 116    8  16 144   48   0 136   68   0 100   92   0  48   84   4   0   60  24   0   32  42   0    8  58   0    0  64   0    0  60   0    0  50  60    0   0   0    0   0   0    0   0   0
152 150 152    8  76 196   48  50 236   92  30 228  136  20 176  160  20 100  152  34  32  120  60   0   84  90   0   40 114   0    8 124   0    0 118  40    0 102 120    0   0   0    0   0   0    0   0   0
236 238 236   76 154 236  120 124 236  176  98 236  228  84 236  236  88 180  236 106 100  212 136  32  160 170   0  116 196   0   76 208  32   56 204 108   56 180 204   60  60  60    0   0   0    0   0   0
236 238 236  168 204 236  188 188 236  212 178 236  236 174 236  236 174 212  236 180 176  228 196 144  204 210 120  180 222 120  168 226 144  152 226 180  160 214 228  160 162 160    0   0   0    0   0   0"""
nes_pal = np.array(list(map(int, re.split(r"\s+", _nes_pal_str.strip()))), np.uint8).reshape(-1, 3)

num_terrains = 0x16
num_terrain_names = 0x10
num_metatiles = 0xd0
num_units = 0x16
num_pcs = 0x35
num_items = 0x5c
num_maps = 0x19

class PacketHeader(LittleEndianStructure):
	_pack_ = True
	_fields_ = (
		("ppu_addr", c_uint16_be),
		("size", c_uint8),
	)

class Packet:
	def __init__(self, rom, hdr_offs):
		self.hdr = PacketHeader.from_buffer(rom, hdr_offs)
		self.data = (c_uint8 * self.hdr.size).from_buffer(rom, hdr_offs + sizeof(self.hdr))

class Metatile(Structure):
	_pack_ = True
	_fields_ = (
		("tl", c_uint8),
		("tr", c_uint8),
		("bl", c_uint8),
		("br", c_uint8),
	)

BankAnimFrame = namedtuple("BankAnimFrame", ("bank", "num_frames"))

class YxCoordinate(Structure):
	_pack_ = True
	_fields_ = (
		("y", c_uint8),
		("x", c_uint8),
	)

class SpriteAttribs(Structure):
	_pack_ = True
	_fields_ = (
		("attribs", c_uint8),
		("y", c_int8),
		("x", c_int8),
	)

class SpriteFacing(IntEnum):
	Up = 0
	Right = 1
	Down = 2
	Left = 3

Metasprite = namedtuple("Metasprite", ("tile_attribs", "tile_idcs"))
class MetaspriteType2Sprite(Structure):
	_pack_ = True
	_fields_ = (
		("y", c_int8),
		("tile_idx", c_uint8),
		("attribs", c_uint8),
		("x", c_int8),
	)

MetaspriteFrameIndices = (c_uint8 * 2) * 4
UnitSpriteInfo = namedtuple("UnitSpriteInfo", ("bank_idx", "tbl_idx", "sprite_tbl", "chr_bank_idx", "frame_idcs", "right_facing_is_flipped"))

Portrait = namedtuple("Portrait", ("bank_idx", "pal_idx", "sprite_idx", "frame_sprite_idcs", "frame_times"))

class TerrainTypes(IntEnum):
	Plain = 0
	UnusedFloor = 1
	Town1 = 2
	Fort = 3
	Castle = 4
	Forest = 5
	Desert = 6
	River = 7
	MountainHill = 8
	MountainPeak = 9
	Bridge = 0xa
	Ocean = 0xb
	Floor = 0xc
	Sky = 0xd
	InvalidNpc = 0xe
	Town2 = 0xf
	Pillar = 0x10
	Stairs = 0x11
	TreasureChest = 0x12
	Town3 = 0x13
	Town4 = 0x14
	Wall = 0x15
	InvalidPc = 0x1f

class UnitTypes(IntEnum):
	SocialKnight = 1
	ArmorKnight = 2
	PegasusKnight = 3
	Paladin = 4
	DragonKnight = 5
	Mercenary = 6
	Fighter = 7
	Pirate = 8
	Thief = 9
	Hero = 0xa
	Archer = 0xb
	Hunter = 0xc
	Shooter = 0xd
	Horseman = 0xe
	Sniper = 0xf
	Commando = 0x10
	Mamkute = 0x11
	Mage = 0x12
	Cleric = 0x13
	Bishop = 0x14
	Lord = 0x15
	General = 0x16

	# Special-purpose types only used in specific circumstances
	Dragon = 0x17 # Mamkute transformed form
	EarthDragon = 0x18

class CharGrowthChanceInfo(Structure):
	_pack_ = True
	_fields_ = [(name, c_uint8) for name in "strength skill wpn_lvl speed luck defense hp".split()]

class EnemyUnitTypeInfo(Structure):
	_pack_ = True
	_fields_ = [(name, c_uint8) for name in "strength skill wpn_lvl speed luck defense movement hp xp".split()]

class MapHeader(LittleEndianStructure):
	_pack_ = True
	_fields_ = (
		("metatiles_high", c_uint8),
		("metatiles_wide", c_uint8),
		("initial_scroll_metatile_y", c_uint8),
		("initial_scroll_metatile_x", c_uint8),
	)

MapBankInfo = namedtuple("MapBankInfo", "start_idx end_idx bank_idx map_tbl_addr leca addrs".split())
def MakeMapBankInfo(rom, bank_idx, base_idx, num_maps, map_tbl_addr):
	leca = get_leca4((bank_idx, 15))

	return MapBankInfo(
		base_idx,
		base_idx + num_maps,
		bank_idx,
		map_tbl_addr,
		leca,
		(c_uint16_le * num_maps).from_buffer(rom, leca(map_tbl_addr)),
		)

Map = namedtuple("Map", "map_idx bank addr hdr data".split())

class MapMusicInfo(Structure):
	_pack_ = True
	_fields_ = (
		("early_music_nums", c_uint8 * 2),
		("late_music_nums", c_uint8 * 2),
	)

class MapNpc(LittleEndianStructure):
	_pack_ = True
	_fields_ = (
		("id", c_uint8),
		("type", c_uint8),
		("level", c_uint8),
		("item_idcs", c_uint8 * 2),
		("y", c_uint8),
		("x", c_uint8),
		("item_values", c_uint8 * 4),
	)

class MapPc(LittleEndianStructure):
	_pack_ = True
	_fields_ = (
		("id", c_uint8),
		("type", c_uint8),
		("level", c_uint8),
		("hp", c_uint8),
		("max_hp", c_uint8),
		("xp", c_uint8),
		("bg_metatile", c_uint8),
		("strength", c_uint8),
		("skill", c_uint8),
		("wpn_lvl", c_uint8),
		("speed", c_uint8),
		("luck", c_uint8),
		("defense", c_uint8),
		("movement", c_uint8),
		("unk_e", c_uint8),
		("resistance", c_uint8),
		("y", c_uint8),
		("x", c_uint8),
		("state", c_uint8),
		("item_idcs", c_uint8 * 4),
		("item_values", c_uint8 * 4),
	)

class ShopType(IntEnum):
	Armory = 1
	Shop = 2
	Arena = 3
	Storage = 4
	SecretShop = 5

class MapShop(Structure):
	_pack_ = True
	_fields_ = (
		("y", c_uint8),
		("x", c_uint8),
		("type", c_uint8),
		("inv_idx", c_uint8),
	)

class PreMissionInfo(Structure):
	_pack_ = True
	_fields_ = (
		("dialog_idx", c_uint8),
		("music_num", c_uint8),
	)

class MissionDialogInfo(Structure):
	_pack_ = True
	_fields_ = (
		("y", c_uint8),
		("x", c_uint8),
		("action", c_uint8),
		("dialog_idx", c_uint8),
		("music_num", c_uint8),
	)

ScriptInfo = namedtuple("ScriptInfo", ("bank_idx", "set_idx", "script_idx", "script_addr", "script", "op_infos"))

class FireEmblem1Data:
	def __init__(self, rom):
		rom = self._rom = rom
		hdr = self._hdr = iNesHeader.from_buffer(rom)

		if hdr.sig != b"NES\x1a" or hdr.num_prg_16kbs != 0x10 or hdr.num_chr_8kbs != 0x10 or hdr.flags7 != 0:
			raise ValueError("ROM does not appear to be Fire Emblem")

		chr_start_offs = self._chr_start_offs = hdr.num_prg_16kbs * 0x4000 + 0x10
		num_chr_banks = hdr.num_chr_8kbs * 2
		self.tile_banks = (TileBank * num_chr_banks).from_buffer(rom, chr_start_offs)
		self.tile_banks_data = np.frombuffer(rom, np.uint8, sizeof(self.tile_banks), chr_start_offs).reshape((num_chr_banks, 256, 2, 8))

		self._load_terrain_data()

		self._map_rom_banks = (6, 15)
		self._map_leca = get_leca4(self._map_rom_banks)
		self._load_map_gfx()		
		self._load_map_data()
		self._load_map_obj_data()

		self.port_leca = get_leca4((10, 15))
		self._load_port_gfx()
		self._load_port_infos()

		self._load_unit_data()
		self._load_item_data()

		self._load_text()

		return

	def _load_terrain_data(self):
		rom = self._rom
		leca = self.terrain_img_leca = get_leca4((5, 15))

		self.pc_metatile_terrain_types = (c_uint8 * num_metatiles).from_buffer(rom, leca(0xe828))
		self.npc_metatile_terrain_types = (c_uint8 * num_metatiles).from_buffer(rom, leca(0xe8f8))
		self.terrain_dodge_chances = (c_uint8 * num_terrains).from_buffer(rom, leca(0xebd8))
		self.terrain_name_idcs = (c_uint8 * num_terrains).from_buffer(rom, leca(0xebee))

		self.unit_terrain_cost_addrs = (c_uint16_le * 0x16).from_buffer(rom, leca(0xe9c8))
		self.unit_terrain_costs = [
			(c_uint8 * num_terrains).from_buffer(rom, leca(addr)) 
			for addr in self.unit_terrain_cost_addrs
		]

		self.terrain_img_metasprite_list_addr = c_uint16_le.from_buffer(rom, leca(0xbfd0)).value
		self.terrain_img_metasprite_addrs = (c_uint16_le * num_terrain_names).from_buffer(rom, leca(self.terrain_img_metasprite_list_addr))
		self.terrain_img_metasprites = [
			self._load_metasprite_type2(leca(addr))
			for addr in self.terrain_img_metasprite_addrs
		]

		return

	def _load_map_gfx(self):
		rom = self._rom
		leca = self._map_leca

		self.map_pal_pack_addrs_addr = 0xbfc0
		pal_pack_addrs_addr = c_uint16_le.from_buffer(rom, leca(0xbfc0)).value
		self.map_pal_pack_addrs = (c_uint16_le * 8).from_buffer(rom, leca(pal_pack_addrs_addr))

		self.pal_packs = []
		for pack_addr in self.map_pal_pack_addrs:
			self.pal_packs.append(Packet(rom, leca(pack_addr)))

		metatile_offs = leca(0x8000)
		self.metatiles = (Metatile * 256).from_buffer(rom, metatile_offs) # Not clear if 0xd0 or 256
		self.metatile_arrays = np.frombuffer(rom, np.uint8, sizeof(self.metatiles), metatile_offs).reshape((-1, 2, 2))
		self.metatile_attribs = np.frombuffer(rom, np.uint8, len(self.metatiles), leca(0xf1bf))

		anim_frame_banks = (c_uint8 * 4).from_buffer(rom, leca(0xc1e4))
		anim_frame_lengths = (c_uint8 * 4).from_buffer(rom, leca(0xc1e8))

		self.map_anim_banks = [BankAnimFrame(*x) for x in zip(anim_frame_banks, anim_frame_lengths)]

		leca = get_leca4((11, 15))
		num_sprites = 0x16
		
		self.map_sprite_bank = 8
		self.map_sprite_sprite_idx = 0
		self.map_sprite_frame_idcs = (MetaspriteFrameIndices * num_sprites).from_buffer(rom, leca(0xb0aa))
		self.map_sprite_pal_idcs = (c_uint8 * 2).from_buffer(rom, leca(0xb15a)) # First index for player, second for enemy
		self.map_sprite_right_modes = (c_uint8 * num_sprites).from_buffer(rom, leca(0xb15c)) # If non-0 right facing is mirroed horizontally
		self.map_sprite_chr_banks = (c_uint8 * num_sprites).from_buffer(rom, leca(0xb172))

		leca = get_leca4((self.map_sprite_bank, 15))
		self.map_sprite_tbls_addr = (c_uint16_le * 1).from_buffer(rom, leca(0xbfd0))
		sprite_addrs = self.map_sprite_addr_tbls = [(c_uint16_le * 0x60).from_buffer(rom, leca(self.map_sprite_tbls_addr[0]))]
		sprites = [self._load_metasprite(leca, addr) for addr in sprite_addrs[0]]
		self.map_sprite_tbls = [sprites]
		
		self.map_sprites = []
		for sprite_idx in range(num_sprites):
			sprite = UnitSpriteInfo(
				self.map_sprite_bank,
				self.map_sprite_sprite_idx,
				self.map_sprite_tbls[self.map_sprite_sprite_idx],
				self.map_sprite_chr_banks[sprite_idx],
				self.map_sprite_frame_idcs[sprite_idx],
				self.map_sprite_right_modes[sprite_idx],
			)
			self.map_sprites.append(sprite)

		return

	def _load_map_data(self):
		rom = self._rom
		leca = self._map_leca

		self.map_banks = [MakeMapBankInfo(*x) for x in (
			(rom, 2, 1, 13, 0x8000),
			(rom, 9, 14, 12, 0x8000),
		)]
		self.maps = {}
		for bank in self.map_banks:
			for map_idx in range(bank.start_idx, bank.end_idx):
				addr = bank.addrs[map_idx - bank.start_idx]
				offs = bank.leca(addr)

				hdr = MapHeader.from_buffer(rom, offs)
				size = (hdr.metatiles_high + 1, hdr.metatiles_wide + 1)
				data = np.frombuffer(
					rom, 
					np.uint8, 
					size[0] * size[1],
					offs + sizeof(hdr),
				).reshape(size)

				self.maps[map_idx] = Map(map_idx, bank.bank_idx, addr, hdr, data)

		self.map_music_info = MapMusicInfo.from_buffer(rom, leca(0xb9ac))
		self.last_map_music_info = (c_uint8 * 2).from_buffer(rom, leca(0xb9b0))

	def _load_map_obj_data(self):
		rom = self._rom
		leca = self.map_obj_leca = get_leca4((8, 15))

		self.map_npc_list_addrs, self.map_npc_lists = load_term_dicts(
			rom, leca, 0x8aa3, num_maps, ty = MapNpc, terms = 0, base_idx = 1)
		self.map_pc_list_addrs, self.map_pc_lists = load_term_dicts(
			rom, leca, 0x8490, num_maps, ty = MapPc, terms = 0, base_idx = 1)

		self.map_start_loc_list_addrs = (c_uint16_le * num_maps).from_buffer(rom, leca(0x8790))
		self.map_start_loc_lists = {}
		for map_idx, list_addr in enumerate(self.map_start_loc_list_addrs):
			offs = leca(list_addr)
			num_entries = rom[offs]
			
			l = (YxCoordinate * num_entries).from_buffer(rom, offs + 1) if num_entries else []
			self.map_start_loc_lists[map_idx + 1] = l

		leca = self.map_shop_leca = get_leca4((11, 15))
		self.map_shop_list_addrs, self.map_shop_lists = load_term_dicts(
			rom, leca, 0xa4ff, num_maps, ty = MapShop, terms = 0xf0)
		self.inv_list_addrs, self.inv_lists = load_term_lists(
			rom, leca, 0xa6c2, 20, terms = 0xf0)

		leca = self.map_dlg_pc_lists = get_leca4((3, 15))
		self.map_dlg_pc_list_addrs = (c_uint16_le * num_maps).from_buffer(rom, leca(0x9466))
		self.map_dlg_pc_lists = [
			(MapPc * 2).from_buffer(rom, leca(addr))
			for addr in self.map_dlg_pc_list_addrs
		]

		return

	def _load_port_gfx(self):
		rom = self._rom
		leca = self.port_leca

		self.port_chr_bank_idcs = (c_uint8 * 0x4f).from_buffer(rom, leca(0x8a14))

		self.port_pal_pack_addrs = (c_uint16_le * 0x50).from_buffer(rom, leca(0xb71c))
		self.port_pal_idcs = (c_uint8 * 0x4f).from_buffer(rom, leca(0x8a63))
		self.port_pal_packs = []
		for pack_addr in self.port_pal_pack_addrs:
			self.port_pal_packs.append(Packet(rom, leca(pack_addr)))
		
		self.port_sprite_tbl_addrs = (c_uint16_le * 1).from_buffer(rom, leca(0xbfd0))
		self.port_sprite_addr_tbls = [(c_uint16_le * 0xff).from_buffer(rom, leca(self.port_sprite_tbl_addrs[0]))]

		self.port_sprites = []
		for tbl_idx, addrs in enumerate(self.port_sprite_addr_tbls):
			tbl_sprites = [self._load_metasprite(leca, addr) for addr in addrs]
			self.port_sprites.append(tbl_sprites)
		
	def _load_port_infos(self):
		rom = self._rom
		leca = self.port_leca

		self.port_base_sprite_num = (c_uint8 * 0x4f).from_buffer(rom, leca(0x89c5))
		self.port_frame_sprite_list_addrs = (c_uint16_le * 0x4f).from_buffer(rom, leca(0x8795))
		self.port_frame_times_list_addrs, times_lists = load_term_lists(
			rom, leca, 0x88e2, 0x4f, terms = 0xf0)
		self.port_infos = []
		for port_idx, times_list in enumerate(times_lists):
			sprite_list_addr = self.port_frame_sprite_list_addrs[port_idx]
			sprite_list_offs = leca(sprite_list_addr)
			sprite_list = (c_uint8 * len(times_list)).from_buffer(rom, sprite_list_offs)

			self.port_infos.append(Portrait(
				self.port_chr_bank_idcs[port_idx],
				self.port_pal_idcs[port_idx],
				self.port_base_sprite_num[port_idx],
				sprite_list,
				times_list,
			))

		return
	
	def _load_unit_data(self):
		rom = self._rom
		leca = get_leca4((0, 15))

		self.unit_type_info_addrs = (c_uint16_le * num_units).from_buffer(rom, leca(0xec04))
		self.unit_type_infos = [
			EnemyUnitTypeInfo.from_buffer(rom, leca(addr))
			for addr in self.unit_type_info_addrs
		]

		self.char_growth_info_addrs = (c_uint16_le * num_pcs).from_buffer(rom, leca(0xe1e0))
		self.char_growth_infos = [
			CharGrowthChanceInfo.from_buffer(rom, leca(addr)) 
			for addr in self.char_growth_info_addrs
		]

		offs = leca(0xedb5)
		num_entries = rom.index(0, offs, self._chr_start_offs) - offs
		self.talk_src_pc_ids = (c_uint8 * num_entries).from_buffer(rom, offs)
		self.talk_tgt_npc_ids = (c_uint8 * num_entries).from_buffer(rom, leca(0xedc4))
		self.talk_script_idcs = (c_uint8 * num_entries).from_buffer(rom, leca(0xedd2))
		self.talk_tgt_new_pc_ids = (c_uint8 * num_entries).from_buffer(rom, leca(0xede0))

		return

	def _load_item_data(self):
		rom = self._rom
		leca = self.item_info_leca = get_leca4((6, 15))
		load_byte_tbl = lambda x: (c_uint8 * num_items).from_buffer(rom, leca(x))
		load_byte_lists = lambda addr, num_entries, terms: load_term_lists(rom, leca, addr, num_entries, terms = terms, end_offs = self._chr_start_offs)

		self.item_mights = load_byte_tbl(0xd657)
		self.item_reqs = load_byte_tbl(0xd6b3)
		self.item_weights = load_byte_tbl(0xd70f)
		self.item_hit_chances = load_byte_tbl(0xd76b)
		self.item_crit_chances = load_byte_tbl(0xd7c7)
		self.item_prices = load_byte_tbl(0xd823)
		self.item_uses = load_byte_tbl(0xd87f)
		self.item_effects = load_byte_tbl(0xd967)
		self.item_flags = load_byte_tbl(0xd9c3)

		self.item_class_equip_none = 0xfe
		self.item_class_equip_base = 0

		self.item_strong_against_idcs = load_byte_tbl(0xd8db)
		self.item_strong_against_tbl_addrs, self.item_strong_against_tbls = load_byte_lists(0xd937, 11, 0xff)
		self.item_strong_against_none = 0
		self.item_strong_against_base = 1

	def _load_text(self):
		rom = self._rom
		leca = self.miss_info_leca = get_leca4((3, 15))

		self.text = None
		for text_mod in (text_original, text_polinym):
			if text_mod.TextData.is_rom(rom):
				self.text = text_mod.TextData(rom, self._chr_start_offs)
				break

		assert self.text

		self.get_script_addrs = self.text.get_script_addrs
		self.translate_text = self.text.translate_text

		self.terrain_names = self.text.terrain_names
		self.unit_names = self.text.unit_names
		self.char_names = self.text.char_names
		self.enemy_names = self.text.enemy_names
		self.item_names = self.text.item_names
		self.miss_names = self.text.miss_names
		self.loc_names = self.text.loc_names
		self.game_strs = self.text.game_strs

		self.pre_miss_info_addrs = (c_uint16_le * 0x19).from_buffer(rom, leca(0xa08d))
		self.miss_dlg_addrs = (c_uint16_le * 0x19).from_buffer(rom, leca(0xa0f1))

		self.pre_miss_script_bank_set = (8, 0)
		self.miss_dlg_script_bank_set = (12, 0)

		self.item_class_equip_idcs = self.text.item_class_equip_idcs
		self.item_class_equip_tbl_addrs = self.text.item_class_equip_tbl_addrs
		self.item_class_equip_tbls = self.text.item_class_equip_tbls

		return

	def _load_metasprite(self, leca, sprite_addr):
		rom = self._rom

		sprite_offs = leca(sprite_addr)
		attribs_addr = c_uint16_le.from_buffer(rom, sprite_offs).value
		attribs_offs = leca(attribs_addr)
		num_tiles = rom[attribs_offs::sizeof(SpriteAttribs)].index(0xf0)
		tile_attribs = (SpriteAttribs * num_tiles).from_buffer(rom, attribs_offs)
		tile_idcs = (c_uint8 * num_tiles).from_buffer(rom, sprite_offs + 2)

		return Metasprite(tile_attribs, tile_idcs)

	def _load_metasprite_type2(self, metasprite_offs):
		rom = self._rom

		num_parts = rom[metasprite_offs]
		return (MetaspriteType2Sprite * num_parts).from_buffer(rom, metasprite_offs + 1)

	def get_pre_miss_info(self, miss_idx):
		return PreMissionInfo.from_buffer(self._rom, self.miss_info_leca(self.pre_miss_info_addrs[miss_idx - 1]))

	def get_miss_dlg_info(self, miss_idx):
		offs = self.miss_info_leca(self.miss_dlg_addrs[miss_idx - 1])
		num_infos = self._rom[offs::sizeof(MissionDialogInfo)].index(0)
		infos = (MissionDialogInfo * num_infos).from_buffer(self._rom, offs)

		return infos

	def get_chr_bank_array(self, bank_idx):
		bank_data = np.unpackbits(self.tile_banks_data[bank_idx]).reshape((256, 2, 8, 8)).transpose(1, 0, 2, 3)

		comb_data = bank_data[0] + (bank_data[1] << 1)
		return ma.masked_equal(comb_data, 0)

	def get_palette_pack_array(self, pack, sprite_pal = False):
		if sprite_pal:
			ppu_addr = 0x3f10
		else:
			ppu_addr = 0x3f00

		assert pack.hdr.ppu_addr <= ppu_addr and pack.hdr.ppu_addr + pack.hdr.size >= ppu_addr + 0x10
		
		start_offs = ppu_addr - pack.hdr.ppu_addr
		pal = np.frombuffer(pack.data, np.uint8, 0x10, start_offs).reshape((-1, 4))

		if ppu_addr == 0x3f00:
			pal[0:3, 0] = pal[0, 0]

		return pal.flatten()

	def get_palette_array(self, pack_idx, sprite_pal = False):
		pack = self.pal_packs[pack_idx]

		return self.get_palette_pack_array(pack, sprite_pal)

	def get_port_palette_array(self, pal_idx):
		pack = self.port_pal_packs[pal_idx]

		return self.get_palette_pack_array(pack, True)

	def get_nes_palette_array(self, pack_idx, sprite_pal = False):
		pal = self.get_palette_array(pack_idx, sprite_pal)

		return nes_pal[pal]

	def get_remap_palette_array(self, palette, is_rgb):
		pal_map = {}
		for idx, pal_idx in enumerate(palette):
			pal_map.setdefault(tuple(pal_idx) if is_rgb else pal_idx, idx)

		return np.asarray([pal_map[tuple(pal) if is_rgb else pal] for pal in palette], np.uint8)

	def get_map_tilemap(self, _map):
		mtile_map = self.metatile_arrays
		tile_map = mtile_map[_map].transpose(0, 2, 1, 3).reshape((_map.shape[0] * 2, -1))
		attrib_map = self.metatile_attribs[_map]

		return tile_map, attrib_map

	def get_tiles_bitmap(self, chr_bank, tiles, attribs):
		bitmap = chr_bank[tiles].transpose(0, 2, 1, 3).reshape((tiles.shape[0] * 8, -1))
		bitmap += np.repeat(np.repeat((attribs & 3) << 2, 16, 0), 16, 1)

		return bitmap

	def get_map_bitmap(self, chr_bank, _map):
		tiles, attribs = self.get_map_tilemap(_map)

		return self.get_tiles_bitmap(chr_bank, tiles, attribs)

	def get_map_bank(self, map_idx):
		for bank in self.map_banks:
			if map_idx >= bank.start_idx and map_idx < bank.end_idx:
				return bank

		raise IndexError(f"Map {map_idx} does not exist")

	def get_map_array(self, map_idx):
		mp = self.maps[map_idx]

		return mp.data

	def get_map_objs(self, map_idx):
		return self.map_npc_lists[map_idx], self.map_pc_lists[map_idx]

	def merge_map_array_with_objs(self, mp, np_objs, pc_objs):
		merged = mp.copy()

		for objs, color in ((np_objs, 1), (pc_objs, 0)):
			for obj in objs:
				merged[obj.y, obj.x] = obj.type * 2 + color

		return merged

	def get_sprite_size(self, sprite):
		arr = np.frombuffer(sprite.tile_attribs, np.uint8).reshape((-1, 3))

		return arr[:, 2].max() + 8, arr[:, 1].max() + 8

	def draw_sprite(self, bitmap, chr_bank, sprite, x = 0, y = 0, *, pal_idx = 0, hflipped = False, v38 = 0):
		flip_axes_lists = (tuple(), (1,), (0,), (0, 1))
		hflip_flag = 0x40 if hflipped else 0

		for frame_idx, attribs in enumerate(reversed(sprite.tile_attribs)):
			tile_y = y + attribs.y
			tile_x = x + (-attribs.x - 8 if hflipped else attribs.x)
			sprite_attribs = (attribs.attribs | v38 | pal_idx) ^ hflip_flag
			tile_idx = sprite.tile_idcs[-1 - frame_idx]
			
			tile = chr_bank[tile_idx] + (sprite_attribs & 3) * 4
			flip_axes = flip_axes_lists[sprite_attribs >> 6]
			if flip_axes:
				tile = np.flip(tile, flip_axes)

			tgt = bitmap[tile_y:tile_y+8, tile_x:tile_x+8]
			ma.choose(tile.mask, (tile, tgt), out = tgt)

	def draw_sprite_type2(self, bitmap, chr_bank, metasprite, x = 0, y = 0, *, pal_idx = None, hflipped = False, pre_set_bits = 0, clear_bits = 0, post_set_bits = 0):
		flip_axes_lists = (tuple(), (1,), (0,), (0, 1))
		hflip_flag = 0x40 if hflipped else 0
		
		if pal_idx is not None:
			post_set_bits |= pal_idx
			clear_bits |= 3

		set_bits = post_set_bits | (pre_set_bits & ~clear_bits)

		for part in metasprite:
			tile_y = y + part.y
			tile_x = x + (8 - part.x if hflipped else part.x)
			attribs = ((part.attribs & ~clear_bits) | set_bits) ^ hflip_flag

			tile = chr_bank[part.tile_idx] + (attribs & 3) * 4
			flip_axes = flip_axes_lists[attribs >> 6]
			if flip_axes:
				tile = np.flip(tile, flip_axes)

			tgt = bitmap[tile_y:tile_y+8, tile_x:tile_x+8]
			ma.choose(tile.mask, (tile, tgt), out = tgt)

	def draw_sprite_frames(
		self, 
		bitmaps, 
		chr_bank, 
		frames, 
		x = 0, 
		y = 0, 
		*, 
		pal_idx = 0, 
		hflipped = False, 
		v38 = 0,
		):

		for frame_idx, frame in enumerate(frames):
			self.draw_sprite(
				bitmaps[frame_idx], 
				chr_bank, 
				frame, 
				x, 
				y, 
				pal_idx = pal_idx, 
				hflipped = hflipped, 
				v38 = v38,
			)

	def draw_portrait(self, port, *, chr_bank = None, hflipped = False, v38 = 0, v39 = 0):
		port_size = (64, 64)

		if not chr_bank:
			chr_bank = self.get_chr_bank_array(port.bank_idx)

		sprite = self.port_sprites[0][port.sprite_idx]
		static_bmp = ma.masked_all(port_size, np.uint8)
		self.draw_sprite(static_bmp, chr_bank, sprite)
		
		frame_dims = np.zeros((len(port.frame_sprite_idcs) + 1, 2), int)
		frame_dims[-1] = self.get_sprite_size(sprite)

		bitmap = ma.masked_all((len(port.frame_sprite_idcs),) + port_size, np.uint8)
		for frame_idx, sprite_idx in enumerate(port.frame_sprite_idcs):
			sprite = self.port_sprites[0][sprite_idx]
			frame_dims[frame_idx,:] = self.get_sprite_size(sprite)
			
			frame_bmp = bitmap[frame_idx]
			self.draw_sprite(frame_bmp, chr_bank, sprite)
			ma.choose(static_bmp.mask, (static_bmp, frame_bmp), out = frame_bmp)

		return bitmap[:, 0:frame_dims[:,1].max(), 0:frame_dims[:,0].max()]

	def get_script_ids(self, bank_idx = None, set_idx = None):
		addrs_tree = self.get_script_addrs()
		script_ids = []

		if bank_idx is None:
			for bank_idx, script_bank in addrs_tree.items():
				for set_idx, script_addrs in enumerate(script_bank):
					prefix = (bank_idx, set_idx)
					script_ids.extend((prefix + (script_idx,) for script_idx in range(len(script_addrs))))

		elif set_idx is None:
			for set_idx, script_addrs in enumerate(addrs_tree[bank_idx]):
				prefix = (bank_idx, set_idx)
				script_ids.extend((prefix + (script_idx,) for script_idx in range(len(script_addrs))))

		else:
			prefix = (bank_idx, set_idx)
			script_addrs = addrs_tree[bank_idx][set_idx]
			script_ids.extend((prefix + (script_idx,) for script_idx in range(len(script_addrs))))

		return script_ids

	def get_script_addr(self, bank_idx, set_idx, script_idx):
		return self.get_script_addrs()[bank_idx][set_idx][script_idx]

	def get_script(self, bank_idx, set_idx, script_idx):
		script_iter = self.text.get_script_iter(bank_idx, set_idx, script_idx)

		return ScriptInfo(
			bank_idx, 
			set_idx, 
			script_idx, 
			self.text.get_script_addrs()[bank_idx][set_idx][script_idx], 
			*self._get_script(script_iter),
		)

	def _get_script(self, script_iter):
		opcode_re = re.compile(rb"[\xdf-\xef]")
		op_lens = {i + ScriptOps.PlaySound: size for i, size in enumerate((2, 1, 2, 1, 1, -3, 6, -3, -1, 6, 2, 1, 1, 2, 1, 1, -1))}

		cur_offs = 0
		script = bytearray()
		ops_offs = []
		end_offs = -1
		for seg in script_iter:
			#print(bytes(seg).hex())

			script.extend(seg)

			if len(script) <= cur_offs:
				continue
			elif end_offs >= 0 and len(script) >= end_offs:
				break

			match = opcode_re.search(script, cur_offs)
			while match:
				start_offs = match.start()
				byte = script[start_offs]
				op_len = op_lens[byte]
				#print(f"<<{byte:02x} @{start_offs}: {op_len}>>")

				ops_offs.append((start_offs, abs(op_len)))
				if op_len > 0:
					cur_offs = start_offs + op_len
				else:
					end_offs = cur_offs = start_offs - op_len

					break

				match = opcode_re.search(script, cur_offs)

			if end_offs >= 0 and len(script) >= end_offs:
				break

			if not match:
				cur_offs = len(script)

		if len(script) > end_offs:
			del script[end_offs:]

		if hasattr(script_iter, "cmp_bytes"):
			cmp_frac = script_iter.cmp_bytes / script_iter.total_bytes

		return script, ops_offs

	def get_unit_obj_for_map_npc(self, npc, is_first = False):
		info = self.unit_type_infos[npc.type - 1]
		lvl = npc.level - 1
		lvl2 = lvl // 2
		hp = info.hp + 3 * lvl2

		obj = MapPc(
			npc.id,
			npc.type,
			npc.level,
			hp,
			hp,
			info.xp + lvl + (10 if is_first else 0),
			0,
			info.strength + lvl2,
			info.skill + lvl2,
			info.wpn_lvl + lvl2,
			info.speed + lvl2,
			info.luck,
			info.defense + lvl2,
			info.movement,
			0,
			0,
			npc.y,
			npc.x,
			0,
			(npc.item_idcs[0], npc.item_idcs[1], 0, 0),
			npc.item_values,
		)

		return obj
		