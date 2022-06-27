"""	
	fe1dump
	Dumping Utility for Fire Emblem: Shadow Dragon and the Blade of Light (NES)
	Copyright 2022 Justin Olbrantz (Quantam)

	This work is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License. To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.
"""

from collections import namedtuple
from ctypes import *
import functools
import itertools
import numpy as np
import numpy.ma as ma
from pathlib import Path
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFile
import PIL.ImageFont
import PIL.ImagePalette
import re
import sys

Image = PIL.Image
ImagePalette = PIL.ImagePalette.ImagePalette

nes_pal_str = """ 84  84  84    0  30 116    8  16 144   48   0 136   68   0 100   92   0  48   84   4   0   60  24   0   32  42   0    8  58   0    0  64   0    0  60   0    0  50  60    0   0   0    0   0   0    0   0   0
152 150 152    8  76 196   48  50 236   92  30 228  136  20 176  160  20 100  152  34  32  120  60   0   84  90   0   40 114   0    8 124   0    0 118  40    0 102 120    0   0   0    0   0   0    0   0   0
236 238 236   76 154 236  120 124 236  176  98 236  228  84 236  236  88 180  236 106 100  212 136  32  160 170   0  116 196   0   76 208  32   56 204 108   56 180 204   60  60  60    0   0   0    0   0   0
236 238 236  168 204 236  188 188 236  212 178 236  236 174 236  236 174 212  236 180 176  228 196 144  204 210 120  180 222 120  168 226 144  152 226 180  160 214 228  160 162 160    0   0   0    0   0   0"""
nes_pal = np.array(list(map(int, re.sub(r"\s+", " ", nes_pal_str.strip()).split())), np.uint8).reshape(4, 16, 3)

c_uint16_le = c_uint16.__ctype_le__
c_uint16_be = c_uint16.__ctype_be__

def leca4(banks, addr):
	bank_base = addr & 0xc000
	bank_idx = addr // 0x4000 - 2

	return addr - bank_base + banks[bank_idx] * 0x4000 + 0x10

def get_leca4(banks):
	return functools.partial(leca4, banks)

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
		("y", c_uint8),
		("x", c_uint8),
	)

Metasprite = namedtuple("Metasprite", ("tile_attribs", "tile_idcs"))

Portrait = namedtuple("Portrait", ("bank_idx", "pal_idx", "sprite_idx", "frame_sprite_idcs", "frame_times"))

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

class MapNpObject(LittleEndianStructure):
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

class MapObject(LittleEndianStructure):
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
		("wpn_level", c_uint8),
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

class FireEmblem1Data:
	def __init__(self, rom):
		rom = self._rom = bytearray(rom)
		hdr = self._hdr = iNesHeader.from_buffer(rom)

		if hdr.sig != b"NES\x1a" or hdr.num_prg_16kbs != 0x10 or hdr.num_chr_8kbs != 0x10 or hdr.flags9 != 0:
			raise ValueError("ROM does not appear to be Fire Emblem")

		chr_start_offs = hdr.num_prg_16kbs * 0x4000 + 0x10
		num_chr_banks = hdr.num_chr_8kbs * 2
		self.tile_banks = (TileBank * num_chr_banks).from_buffer(rom, chr_start_offs)
		self.tile_banks_data = np.frombuffer(rom, np.uint8, sizeof(self.tile_banks), chr_start_offs).reshape((num_chr_banks, 256, 2, 8))

		self._map_rom_banks = (6, 15)
		self._map_leca = get_leca4(self._map_rom_banks)
		self._load_map_gfx()		
		self._load_map_data()
		self._load_map_obj_data()

		self.port_leca = get_leca4((10, 15))
		self._load_port_gfx()
		self._load_port_infos()

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
		self.metatiles = (Metatile * 256).from_buffer(rom, metatile_offs)
		self.metatile_arrays = np.frombuffer(rom, np.uint8, sizeof(self.metatiles), metatile_offs).reshape((256, 2, 2))
		self.metatile_attribs = np.frombuffer(rom, np.uint8, 256, leca(0xf1bf))

		self.map_anim_banks = [BankAnimFrame(*x) for x in (
			(0x19, 8),
			(0x15, 14),
			(0x19, 8),
			(0x18, 14),
		)]

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

	def _load_map_obj_data(self):
		rom = self._rom
		leca = self.map_obj_leca = get_leca4((8, 15))

		self.map_npc_list_addrs = (c_uint16_le * 25).from_buffer(rom, leca(0x8aa3))
		self.map_npc_lists = {}
		self.map_pc_list_addrs = (c_uint16_le * 25).from_buffer(rom, leca(0x8490))
		self.map_pc_lists = {}
		
		for addr_list, obj_list, obj_type in (
			(self.map_npc_list_addrs, self.map_npc_lists, MapNpObject),
			(self.map_pc_list_addrs, self.map_pc_lists, MapObject),
		):
			for map_idx, list_addr in enumerate(addr_list):
				offs = list_offs = leca(list_addr)
			
				num_objs = 0
				while rom[offs] != 0:
					offs += sizeof(obj_type)
					num_objs += 1

				l = (obj_type * num_objs).from_buffer(rom, list_offs) if num_objs else []
				obj_list[map_idx + 1] = l

		self.map_start_loc_list_addrs = (c_uint16_le * 25).from_buffer(rom, leca(0x8790))
		self.map_start_loc_lists = {}
		for map_idx, list_addr in enumerate(self.map_start_loc_list_addrs):
			offs = leca(list_addr)
			num_entries = rom[offs]
			
			l = (YxCoordinate * num_entries).from_buffer(rom, offs + 1) if num_entries else []
			self.map_start_loc_lists[map_idx + 1] = l

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
			tbl_sprites = []
			for sprite_addr in addrs:
				sprite_offs = leca(sprite_addr)
				attribs_addr = c_uint16_le.from_buffer(rom, sprite_offs).value
				attribs_offs = leca(attribs_addr)
				num_tiles = rom[attribs_offs::sizeof(SpriteAttribs)].index(0xf0)
				tile_attribs = (SpriteAttribs * num_tiles).from_buffer(rom, attribs_offs)
				tile_idcs = (c_uint8 * num_tiles).from_buffer(rom, sprite_offs + 2)

				tbl_sprites.append(Metasprite(tile_attribs, tile_idcs))

			self.port_sprites.append(tbl_sprites)
		
		self.port_base_sprite_num = (c_uint8 * 0x4f).from_buffer(rom, leca(0x89c5))
		self.port_frame_sprite_list_addrs = (c_uint16_le * 0x4f).from_buffer(rom, leca(0x8795))
		self.port_frame_times_list_addrs = (c_uint16_le * 0x4f).from_buffer(rom, leca(0x88e2))

	def _load_port_infos(self):
		rom = self._rom
		leca = self.port_leca

		self.port_infos = []
		for port_idx in range(len(self.port_base_sprite_num)):
			sprite_list_addr = self.port_frame_sprite_list_addrs[port_idx]
			times_list_addr = self.port_frame_times_list_addrs[port_idx]
			sprite_list_offs = leca(sprite_list_addr)
			times_list_offs = leca(times_list_addr)
			num_frames = rom[times_list_offs:].index(0xf0)

			sprite_list = (c_uint8 * num_frames).from_buffer(rom, sprite_list_offs)
			times_list = (c_uint8 * num_frames).from_buffer(rom, times_list_offs)

			self.port_infos.append(Portrait(
				self.port_chr_bank_idcs[port_idx],
				self.port_pal_idcs[port_idx],
				self.port_base_sprite_num[port_idx],
				sprite_list,
				times_list,
			))

		return		

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

		return nes_pal.reshape((-1, 3))[pal]

	def get_remap_palette_array(self, palette, is_rgb):
		pal_map = {}
		for idx, pal_idx in enumerate(palette):
			pal_map.setdefault(tuple(pal_idx) if is_rgb else pal_idx, idx)

		return np.asarray([pal_map[tuple(pal) if is_rgb else pal] for pal in palette], np.uint8)

	def get_map_tilemap(self, _map):
		mtile_map = self.metatile_arrays.reshape((256, 2, 2))
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

	def draw_sprite(self, bitmap, chr_bank, sprite, x = 0, y = 0, *, hflipped = False, v38 = 0, v39 = 0):
		flip_axes_lists = (tuple(), (1,), (0,), (0, 1))

		for frame_idx, attribs in enumerate(reversed(sprite.tile_attribs)):
			# TODO: Implement flipping
			tile_x = x + attribs.x
			tile_y = y + attribs.y
			sprite_attribs = attribs.attribs | v38 | v39
			tile_idx = sprite.tile_idcs[-1 - frame_idx]
			
			tile = chr_bank[tile_idx] + (sprite_attribs & 3) * 4
			flip_axes = flip_axes_lists[sprite_attribs >> 6]
			if flip_axes:
				tile = np.flip(tile, flip_axes)

			tgt = bitmap[tile_y:tile_y+8, tile_x:tile_x+8]
			ma.choose(tile.mask, (tile, tgt), out = tgt)

	def draw_portrait(self, port, *, chr_bank = None, hflipped = False, v38 = 0, v39 = 0):
		port_size = (64, 64)

		if not chr_bank:
			chr_bank = self.get_chr_bank_array(port.bank_idx)

		sprite = self.port_sprites[0][port.sprite_idx]
		static_bmp = ma.masked_all(port_size, np.uint8)
		self.draw_sprite(static_bmp, chr_bank, sprite)
		
		frame_dims = np.zeros((len(port.frame_sprite_idcs) + 1, 2), np.int)
		frame_dims[-1] = self.get_sprite_size(sprite)

		bitmap = ma.masked_all((len(port.frame_sprite_idcs),) + port_size, np.uint8)
		for frame_idx, sprite_idx in enumerate(port.frame_sprite_idcs):
			sprite = self.port_sprites[0][sprite_idx]
			frame_dims[frame_idx,:] = self.get_sprite_size(sprite)
			
			frame_bmp = bitmap[frame_idx]
			self.draw_sprite(frame_bmp, chr_bank, sprite)
			ma.choose(static_bmp.mask, (static_bmp, frame_bmp), out = frame_bmp)

		return bitmap[:, 0:frame_dims[:,1].max(), 0:frame_dims[:,0].max()]

def GetAnimatedMapFrames(data, map_idx, idx_is_data = False):
	pal_array = data.get_nes_palette_array(0)
	palette = ImagePalette("RGB", bytes(pal_array))
	mp = map_idx if idx_is_data else data.get_map_array(map_idx)

	frame_cache = {}
	frames = []
	frame_times = []
	for bank_idx, num_frames in data.map_anim_banks:
		img = frame_cache.get(bank_idx)
		if not img:
			chr_bank = data.get_chr_bank_array(bank_idx)
			bitmap = data.get_map_bitmap(chr_bank, mp)

			img = Image.fromarray(bitmap, "P")
			img.putpalette(palette)

			frame_cache[bank_idx] = img

		frames.append(img)
		frame_times.append(int(round(num_frames * 1000 / 60)))

	return frames, frame_times

def DrawMapStartLocations(frames, start_locs, font, color, outline_color):
	unique_frames = {id(frame): frame for frame in frames}
	for frame in unique_frames.values():
		draw = PIL.ImageDraw.Draw(frame)
		for idx, loc in enumerate(start_locs):
			drawtext = functools.partial(
				draw.text,
				(loc.x * 16 + 8, loc.y * 16 + 8),
				f"{idx + 1}",
				font = font,
				anchor = "mm",
			)

			drawtext(fill = outline_color, stroke_width = 2)
			drawtext(fill = color)

def format_fn(stem, ext = None, number = None, is_anim = False):
	anim_str = " anim" if is_anim else ""
	num_str = f" {number}" if number is not None else ""
	ext_str = f".{ext}" if ext else ""

	if isinstance(stem, Path):
		return stem.parent.joinpath("".join((stem.name, anim_str, num_str, ext_str)))
	else:
		return "".join((stem, anim_str, num_str, ext_str))

def SaveAnimGif(name, number, frames, frame_times):
	frames[0].save(format_fn(name, "gif", number), transparency = -1, optimize = True)
	frames[0].save(
		format_fn(name, "gif", number, True), 
		transparency = -1, 
		optimize = True, 
		save_all = True,
		append_images = frames[1:],
		duration = frame_times,
		loop = 0,
		)

def SaveAnimWebp(name, number, frames, frame_times):
	frames[0].save(
		format_fn(name, "webp", number, True),
		lossless = True, 
		quality = 100, 
		method = 6,
		minimize_size = True,
		save_all = True,
		append_images = frames[1:],
		duration = frame_times,
		loop = 0,
		)

rom = Path(sys.argv[1]).read_bytes()
out_path = Path("out")
out_path.mkdir(exist_ok = True)

data = FireEmblem1Data(rom)

pal_array = data.get_nes_palette_array(0)
remap_pal = data.get_remap_palette_array(pal_array, True)
palette = ImagePalette("RGB", bytes(pal_array))

"""bank_idx = data.bfield_anim_banks[0].bank
chr_bank = data.get_chr_bank_array(bank_idx)
mp = np.arange(0, 256, 1, np.uint8).reshape((16, 16))
bitmap = data.get_map_bitmap(chr_bank, mp)

Path("palette.bin").write_bytes(bytes(palette))
Path("remapping palette.bin").write_bytes(bytes(remap_pal))
Path("raw bitmap.bin").write_bytes(bytes(bitmap.flatten()))

import bad_pillow"""

make_webp = False
a = 0
def SaveAnimImages(name, number, frames, frame_times):
	SaveAnimGif(name, number, frames, frame_times)
	if make_webp:
		SaveAnimWebp(name, number, frames, frame_times)

mp = np.arange(0, 256, 1, np.uint8).reshape((16, 16))
frames, frame_times = GetAnimatedMapFrames(data, mp, True)
frames[0].save(out_path.joinpath("metatiles.png"))
SaveAnimImages(out_path.joinpath("metatiles"), None, frames, frame_times)

for port_idx, port in enumerate(data.port_infos):
	bitmap = data.draw_portrait(port)
	pal = data.get_port_palette_array(port.pal_idx)
	frame_times = [int(round(x * 1000 / 60)) for x in port.frame_times]
	frames = []
	big_frames = []
	for frame in bitmap:
		img = Image.fromarray(frame.filled(0), "P")
		img.putpalette(ImagePalette("RGB", bytes(nes_pal.reshape((-1, 3))[pal])))
		frames.append(img)
		big_frames.append(img.resize((img.width * 4, img.height * 4), Image.Resampling.NEAREST))
	
	SaveAnimImages(out_path.joinpath("portrait"), port_idx, frames, frame_times)
	SaveAnimImages(out_path.joinpath("portrait big"), port_idx, big_frames, frame_times)

font = PIL.ImageFont.truetype("arialbd.ttf", 11)

for map_idx in sorted(data.maps):
	mp = data.get_map_array(map_idx)
	frames, frame_times = GetAnimatedMapFrames(data, mp, True)

	SaveAnimImages(out_path.joinpath("map"), map_idx, frames, frame_times)

	np_objs, pc_objs = data.get_map_objs(map_idx)
	mp = data.merge_map_array_with_objs(mp, np_objs, pc_objs)
	frames, frame_times = GetAnimatedMapFrames(data, mp, True)

	if map_idx > 1:
		DrawMapStartLocations(frames, data.map_start_loc_lists[map_idx], font, 1, 0)

	SaveAnimImages(out_path.joinpath("map objs"), map_idx, frames, frame_times)
	
a = 1