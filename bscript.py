"""	
	fe1dump
	Dumping Utility for Fire Emblem: Shadow Dragon and the Blade of Light (NES)
	Copyright 2022 Justin Olbrantz (Quantam)

	This work is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License. To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.
"""

import numpy as np
import numpy.ma as ma

from common import *
from fe1data import *

class BattleScriptEmu:
	img_tiles = np.array((32, 20), dtype = int)
	img_size = img_tiles * 8

	class SpriteData:
		def __init__(self):
			self.team_idx = 0
			self.sprite_key = None
			self.active = False

			self.chr_bank = None
			self.frame_idx = 0
			self.aux_sprites = []

			self.bg_sprite = True
			self.pos = np.zeros((2,), dtype = int)
			self.pos_offs = self.pos.copy()
			self.inner_attrs = self.remove_attrs = self.outer_attrs = 0
			self.rev_facing = False

			self.mov_iter = self.path_iter = None
			self.rev_mov_dir = False

			self.pause_anim = True
			self.anim_script = self.anim_frame_cnts = None
			self.anim_script_pos = self.anim_frames_left = 0

	def __init__(
		self, 
		data, 
		team_idx, 
		unit, 
		script_idx, 
		init_frame_idx, 
		miss = False, 
		*, 
		chr_banks = None, 
		bg_msprites = None, 
		msprites = None,
	):
		self._data = data
		self._chr_banks = chr_banks or {}
		self._bg_msprites = bg_msprites or {}
		self._msprites = msprites or {}

		self._team_idx = team_idx
		self._unit = unit
		self._unit_idx = unit - 1
		self._init_frame_idx = init_frame_idx
		self._miss = miss

		self._frame_bank_idx, base_idx = (
			data.unit_bsprite_bank_infos[self._unit_idx])
		self._frame_leca = get_leca4((self._frame_bank_idx, 15))
		self._bg_tiles = np.full(self.img_tiles[::-1], 0xff, dtype = np.uint8)
		self._bg_attrs = np.zeros(self.img_tiles[::-1] // 2, dtype = np.uint8)
		self._bg_attrs[:, :self._bg_attrs.shape[1] // 2] = 1
		self._view_offs = np.zeros((2,), dtype = int)
		self._frame_bg = np.zeros(self.img_size[::-1], dtype = np.uint8)
		self._frame_img = np.zeros(self.img_size[::-1], dtype = np.uint8)

		self._script_idx = script_idx
		self._script = data.battle_scripts[script_idx]
		self._script_pos = 0
		self._wait_for_mov = False

		self._script_op_iter = None

		self._frame_ctrs = {}
		self._counter = 0

		self._sprites = [self.SpriteData() for i in range(3)]
		self._sprite = self._sprites[team_idx]
		self._proj_sprite = self._sprites[2]

		self._palette = np.append(
			data.get_palette_pack_array(data.base_battle_pal_pack, False),
			data.get_palette_pack_array(data.base_battle_pal_pack, True),
		).reshape((2, -1, 4))

		chr_bank_idx = data.unit_bsprite_chr_banks[self._unit_idx]
		chr_bank = self._chr_banks.get(chr_bank_idx)
		if not chr_banks:
			chr_bank = data.get_chr_bank_array(chr_bank_idx)
			self._chr_banks[chr_bank_idx] = chr_bank

		init_x_offs = 0x38 + (unit == UnitTypes.DragonKnight) * 8
		for idx, sprite in enumerate(self._sprites[:2]):
			# Not implemented: Mamkute palettes
			pal_idx = data.battle_team_unit_pal_idcs[idx][self._unit_idx]
			self._palette[:, idx, :] = data.battle_pal_rows[pal_idx]

			sprite.team_idx = idx
			sprite.sprite_key = self._unit
			sprite.active = True

			sprite.chr_bank = chr_bank
			sprite.frame_idx = init_frame_idx

			sign = -1 if idx else 1
			sprite.pos[:] = (0x60, 0x78 + init_x_offs * sign)

			if idx:
				sprite.remove_attrs = 3
				sprite.outer_attrs = 1

		self.done = False
		self.total_frames = 0

		self.redraw = self._redraw_bg = self._redraw_sprites = True

	def update(self, num_frames = 1):
		start_frames = self.total_frames

		for i in range(num_frames):
			if not self._update_script():
				self.done = True
				return self.total_frames - start_frames

			for ctr, value in self._frame_ctrs.items():
				self._frame_ctrs[ctr] = max(value - 1, 0)

			self.total_frames += 1

			for sprite in reversed(self._sprites):
				if not sprite.active:
					continue

				self._update_pos(sprite)
				self._update_anim(sprite)

		self.redraw = self._redraw_bg or self._redraw_sprites

		return self.total_frames - start_frames

	def get_frame(self):
		self._render()

		return np.roll(self._frame_img, self._view_offs, (0, 1)), self._palette

	def _update_script(self):
		if self._wait_for_mov:
			return True

		try:
			op = self._script[self._script_pos]
		except IndexError:
			return False

		hdlr = self._hdlrs.get(op.opcode, BattleScriptEmu._error_hdlr)
		cont = hdlr(self, op)

		self._script_pos += not cont

		return True

	def _update_pos(self, sprite):
		if not sprite.mov_iter:
			return

		done = False
		while not done:
			if sprite.path_iter:
				try:
					offs = next(sprite.path_iter)
				except StopIteration:
					sprite.path_iter = None
				else:
					sign = -1 if sprite.rev_mov_dir ^ sprite.team_idx else 1
					offs = (offs.y, offs.x * sign)
					if any(offs):
						sprite.pos += offs
						self._redraw_sprites = True

					done = True

			if not sprite.path_iter:
				try:
					path_idx = next(sprite.mov_iter)
					sprite.path_iter = iter(self._data.bpath_scripts[path_idx])

				except StopIteration:
					sprite.mov_iter = sprite.path_iter = None
					self._wait_for_mov = False

					done = True

		return

	def _update_anim(self, sprite):
		if sprite.pause_anim:
			return

		sprite.anim_frames_left = max(sprite.anim_frames_left - 1, 0)
		if sprite.anim_frames_left:
			return

		sprite.aux_sprites.clear()
			
		done = False
		while not done:
			num_frames = sprite.anim_frame_cnts[sprite.anim_script_pos]
			if num_frames < BAnimScriptFrameOps.Restart:
				frame_idx = sprite.anim_script[sprite.anim_script_pos]
				if frame_idx & 0x80:
					sprite.aux_sprites.append(frame_idx & 0x7f)
					self._redraw_sprites = True

				else:
					if sprite.frame_idx != frame_idx:
						sprite.frame_idx = frame_idx

						if sprite.bg_sprite:
							self._redraw_bg = True
						else:
							self._redraw_sprites = True

					done = True

				sprite.anim_script_pos += 1
				sprite.anim_frames_left = num_frames

			elif num_frames == BAnimScriptFrameOps.Restart:
				sprite.anim_script_pos = 0

			else: # BAnimScriptFrameOps.End
				sprite.pause_anim = True

				done = True

		return

	def _render(self):
		self.redraw = self._redraw_bg or self._redraw_sprites
		if not self.redraw:
			return

		data = self._data
		rom = data._rom
		leca = self._frame_leca
		bank_idx, base_idx = data.unit_bsprite_bank_infos[self._unit_idx]
		bank_unit_idx = self._unit_idx - base_idx

		# Background pass
		if self._redraw_bg:
			for sprite in reversed(self._sprites):
				if not sprite.active or not sprite.bg_sprite:
					continue

				tile_pos = sprite.pos // 8
				facing = sprite.rev_facing ^ sprite.team_idx
				tbl_addr = (data.unit_bsprite_bg_frame_tbl_addrs
					[bank_idx][facing][bank_unit_idx])
				frame_idx = rom[leca(tbl_addr + sprite.frame_idx)]
				key = (sprite.sprite_key, frame_idx)

				msprite = self._bg_msprites.get(key)
				if not msprite:
					addr = data.bsprite_bg_frame_addrs[bank_idx][frame_idx]
					msprite = BgMetasprite(rom, leca(addr))

					self._bg_msprites[key] = msprite

				data.draw_bg_sprite_chrs(
					self._bg_tiles, msprite, *tile_pos[::-1])

			width = self._frame_img.shape[1]
			half_width = width // 2
			for sprite_idx, start_x, end_x in (
				(0, half_width, width),
				(1, 0, half_width),
			):
				start_row = start_x // 8
				end_row = end_x // 8
				chr_bank = self._sprites[sprite_idx].chr_bank
				bg_tiles = self._bg_tiles[:, start_row:end_row]
				self._frame_bg[:, start_x:end_x] = (chr_bank[bg_tiles]
					.transpose(0, 2, 1, 3).reshape((-1, half_width)).filled())
				
			self._frame_bg += (self._bg_attrs * 4).repeat(16, 0).repeat(16, 1)

			self._redraw_bg = False

		# Sprite pass
		self._frame_img[:, :] = self._frame_bg

		for sprite in self._sprites:
			if not sprite.active or sprite.bg_sprite:
				continue

			self._draw_sprite(
				sprite, bank_idx, bank_unit_idx, sprite.frame_idx)

			for frame_idx in sprite.aux_sprites:
				self._draw_sprite(sprite, bank_idx, bank_unit_idx, frame_idx)

		self._redraw_sprites = False
		self.redraw = False

		# Apply view offset in get_frame

		return

	def _draw_sprite(self, sprite, bank_idx, bank_unit_idx, frame_idx):
		data = self._data
		rom = data._rom
		leca = self._frame_leca

		hflipped = sprite.rev_facing ^ sprite.team_idx

		key = (sprite.sprite_key, frame_idx, sprite.inner_attrs, 
			sprite.remove_attrs, sprite.outer_attrs)
		sprite_info = self._msprites.get(key)
		if sprite_info:
			msprite, offs = sprite_info
		else:
			frame_addrs = (data.unit_bsprite_frame_addrs
				  [bank_idx][bank_unit_idx])
			frame_addr = frame_addrs[frame_idx]
			msprite = data._load_metasprite_type2(leca(frame_addr))

			bounds = data.get_sprite_type2_bounds(msprite)
			size = bounds[1] - bounds[0]
			bitmap = ma.masked_all(size, dtype = np.uint8)
			data.draw_sprite_type2(
				bitmap, 
				sprite.chr_bank, 
				msprite, 
				*-bounds[0][::-1],
				hi_pal = True,
				pre_set_bits = sprite.inner_attrs,
				clear_bits = sprite.remove_attrs,
				post_set_bits = sprite.outer_attrs,
			)

			msprite, offs = self._msprites[key] = (bitmap, bounds[0])

		if hflipped:
			msprite = msprite[:, ::-1]
			offs = offs.copy()
			xyz = 16 - (offs[1] + msprite.shape[1])
			offs[1] = data.hflip_sprite_type2_bounds(
				offs[1] + msprite.shape[1])
			assert offs[1] == xyz

		pos = sprite.pos + sprite.pos_offs + offs
		bound = pos + msprite.shape
		mask = ~msprite.mask
		tgt = self._frame_img[pos[0]:bound[0], pos[1]:bound[1]]
		tgt[mask] = msprite[mask]

	def _init_projectile(self, proj_idx):
		data = self._data
		sprite = self._sprite
		proj = self._proj_sprite

		proj.team_idx = sprite.team_idx
		proj.sprite_key = -proj_idx

		proj.bg_sprite = False
		proj.pos[:] = (data.battle_proj_y_pos[proj_idx], sprite.pos[1])
		proj.pos_offs[:] = 0
		proj.inner_attrs = 0x20
		proj.remove_attrs = 3
		proj.outer_attrs = sprite.team_idx

		proj.mov_iter = iter(
			data.bmov_scripts[data.battle_proj_data[proj_idx][1]])
		proj.rev_facing = proj.rev_mov_dir = False

	def _set_sprite_redraw(self, sprite):
		if sprite.bg_sprite:
			self._redraw_bg = True
		else:
			self._redraw_sprites = True

	def _nop_hdlr(self, op):
		return

	def _error_hdlr(self, op):
		raise NotImplementedError()

	def _begin_mov_hdlr(self, op):
		param = op.param
		sprite = self._sprite

		sprite.rev_mov_dir = bool(param & 0x40)
		sprite.mov_iter = iter(self._data.bmov_scripts[param & 0x3f])
		sprite.path_iter = None
		
		self._wait_for_mov = not (param & 0x80)

	def _spawn_anim_proj_hdlr(self, op):
		data = self._data
		proj = self._proj_sprite
		anim_idx = data.battle_proj_data[op.param][0]

		self._init_projectile(op.param)

		proj.chr_bank = self._sprite.chr_bank
		proj.frame_idx = 1
		proj.anim_script = data.banim_scripts[anim_idx]
		proj.anim_frame_cnts = data.banim_script_frame_cnts[anim_idx]
		proj.anim_script_pos = 0
		proj.anim_frames_left = 1
		proj.pause_anim = False

		proj.active = True

		self._redraw_sprites = True

	def _set_counter_hdlr(self, op):
		self._counter = op.param

	def _wait_for_cond_hdlr(self, op):
		if op.param & 0x80:
			self._counter = (self._counter - 1) & 0xff
			wait = bool(self._counter)
		else:
			wait = (self._sprite.frame_idx != op.param)
			
		return wait

	def _set_layers_hdlr(self, op):
		bg = bool(op.param & 2)
		sprite = self._sprite
		if bg != sprite.bg_sprite:
			sprite.bg_sprite = bg
			self._redraw_bg = self._redraw_sprites = True

	def _begin_anim_hdlr(self, op):
		sprite = self._sprite
		sprite.anim_frame_cnts = self._data.banim_script_frame_cnts[op.param]
		sprite.anim_script = self._data.banim_scripts[op.param]
		sprite.anim_script_pos = 0
		sprite.anim_frames_left = 1
		sprite.pause_anim = False

	def _flip_facing_hdlr(self, op):
		sprite = self._sprite
		sprite.rev_facing = not sprite.rev_facing

		self._set_sprite_redraw(sprite)

	def _load_packet_hdlr(self, op):
		packets = self._data.battle_script_packets[op.param ^ (self._team_idx * 2)]
		for packet in packets:
			hdr = packet.hdr
			y, x = divmod(hdr.ppu_addr - 0x2000, 0x20)
			if hdr.vertical:
				self._bg_tiles[y:y + hdr.size, x] = packet.data
			else:
				self._bg_tiles[y, x:x + hdr.size] = packet.data

		self._redraw_bg = True

	def _pause_anim_hdlr(self, op):
		self._sprite.pause_anim = True

	def _resume_anim_hdlr(self, op):
		self._sprite.pause_anim = False

	def _show_hp_hdlr(self, op):
		data = self._data
		team_idx = int(not self._team_idx)

		if not self._script_op_iter:
			wait_frames = self._frame_ctrs.get("death")
			if wait_frames is None:
				self._frame_ctrs["death"] = 0x20

				return True

			elif wait_frames:
				return True

			if self._unit == UnitTypes.PegasusKnight:
				pal_idcs = data.battle_team_peg_death_pal_idcs
			else:
				pal_idcs = data.battle_team_death_pal_idcs 

			self._script_op_iter = iter(pal_idcs[team_idx])

		elif self._frame_ctrs["death"]:
			return True

		try:
			pal_idx = next(self._script_op_iter)
			self._palette[:, team_idx, :] = data.battle_pal_rows[pal_idx]
			self._frame_ctrs["death"] = 8

			self._redraw_bg = True

			return True

		except StopIteration:
			self._frame_ctrs.pop("death")

			return

	def _hit_effect_hdlr(self, op):
		data = self._data
		tgt_team_idx = int(not self._team_idx)
		if not self._script_op_iter:
			self._script_op_iter = iter(data.battle_hit_shake_offs)

			pal_idx = data.battle_team_hit_pal_idcs[tgt_team_idx]
			self._palette[:, tgt_team_idx, :] = data.battle_pal_rows[pal_idx]

		offs = self._view_offs[1] = next(self._script_op_iter)
		if not offs:
			self._script_op_iter = None

			# Not implemented: Mamkute palettes
			pal_idx = (data.battle_team_unit_pal_idcs
				[tgt_team_idx][self._unit_idx])
			self._palette[:, tgt_team_idx, :] = data.battle_pal_rows[pal_idx]

		self._redraw_bg = True

		return offs

	def _sprite_attrs_hdlr(self, op):
		sprite = self._sprite
		if op.param != sprite.inner_attrs:
			sprite.inner_attrs = op.param
			self._redraw_sprites = True

	def _set_x_pos_hdlr(self, op):
		assert self._team_idx == 0

		self._sprite.pos[1] = op.param
		self._redraw_sprites = True

	def _set_frame_hdlr(self, op):
		sprite = self._sprite
		if sprite.frame_idx != op.param:
			sprite.frame_idx = op.param

			self._set_sprite_redraw(sprite)

	def _spawn_proj_hdlr(self, op):
		proj = self._proj_sprite

		self._init_projectile(op.param)

		# NOT implemented: Parthia, Rain Bolt
		if self._unit == UnitTypes.Horseman:
			proj.pos[0] = 0x62

		proj.chr_bank = self._sprite.chr_bank
		proj.frame_idx = self._data.battle_proj_data[op.param][0]
		proj.pause_anim = True

		proj.active = True

		self._redraw_sprites = True
	
	def _wait_for_proj_finish_hdlr(self, op):
		# Missing is not fully implemented
		proj = self._proj_sprite
		if self._miss and proj.mov_iter:
			return True

		proj.mov_iter = proj.path_iter = None
		proj.active = False

	def _wait_for_proj_hit_hdlr(self, op):
		proj = self._proj_sprite
		sprite = self._sprites[not self._team_idx]
		if self._team_idx:
			hit = proj.pos[1] + 16 >= sprite.pos[1]
		else:
			hit = proj.pos[1] - 16 < sprite.pos[1]

		return not hit

	def _wait_for_proj_stop_hdlr(self, op):
		return self._proj_sprite.mov_iter

	def _spawn_unit_proj_hdlr(self, op):
		data = self._data
		proj = self._proj_sprite
		sprite = self._sprite

		chr_bank_idx = data.unit_battle_proj_chr_bank
		proj.chr_bank = self._chr_banks.get(chr_bank_idx)
		if proj.chr_bank is None:
			proj.chr_bank = data.get_chr_bank_array(chr_bank_idx)
			self._chr_banks[chr_bank_idx] = proj.chr_bank

		self._init_projectile(op.param)

		proj.pos[0] += data.unit_battle_proj_y_offs[self._unit_idx]
		proj.mov_iter = iter(data.bmov_scripts[data.unit_proj_bmov_script_idx])
		proj.frame_idx = data.unit_battle_proj_frame_idcs[self._unit_idx]
		proj.pause_anim = True
		proj.active = True

		# Not impemented: Missing, long range

		self._redraw_sprites = True

	def _set_unit_frame_hdlr(self, op):
		sprite = self._sprite
		data = self._data
		frame_idx = data.battle_unit_spec_frame_idcs[self._unit_idx][op.param]
		if frame_idx != sprite.frame_idx:
			sprite.frame_idx = frame_idx

			self._set_sprite_redraw(sprite)

	def _flock_anim_hdlr(self, op):
		self._sprite.pos_offs[1] = (self._data
			.battle_flock_anim_x_offs[self._counter][self.total_frames & 1])

		if not self._frame_ctrs.get("flock", 0):
			self._frame_ctrs["flock"] = 16

			self._counter += 1
			if self._counter >= 7:
				self._frame_ctrs.pop("flock")
					
				return False

		self._redraw_sprites = True

		return True

BattleScriptEmu._hdlrs = {
	BScriptOps.BeginMove: BattleScriptEmu._begin_mov_hdlr,
	BScriptOps.SpawnAnimProjectile: BattleScriptEmu._spawn_anim_proj_hdlr,
	BScriptOps.SetCounter: BattleScriptEmu._set_counter_hdlr,
	BScriptOps.WaitForCondition: BattleScriptEmu._wait_for_cond_hdlr,
	BScriptOps.SetLayers: BattleScriptEmu._set_layers_hdlr,
	BScriptOps.BeginAnim: BattleScriptEmu._begin_anim_hdlr,
	BScriptOps.FlipFacing: BattleScriptEmu._flip_facing_hdlr,
	BScriptOps.LoadPacket: BattleScriptEmu._load_packet_hdlr,
	BScriptOps.PauseAnim: BattleScriptEmu._pause_anim_hdlr,
	BScriptOps.ResumeAnim: BattleScriptEmu._resume_anim_hdlr,
	BScriptOps.ApplyDamage: BattleScriptEmu._nop_hdlr,
	BScriptOps.ShowHpBar: BattleScriptEmu._show_hp_hdlr,
	BScriptOps.ShakeScreen: BattleScriptEmu._hit_effect_hdlr,
	BScriptOps.SpriteAttributes: BattleScriptEmu._sprite_attrs_hdlr,
	BScriptOps.EndOfScript: BattleScriptEmu._error_hdlr,
	BScriptOps.SetXPos: BattleScriptEmu._set_x_pos_hdlr,
	BScriptOps.SetFrame: BattleScriptEmu._set_frame_hdlr,
	BScriptOps.SpawnProjectile: BattleScriptEmu._spawn_proj_hdlr, 
	BScriptOps.WaitForProjFinish: BattleScriptEmu._wait_for_proj_finish_hdlr, 
	BScriptOps.WaitForProjHit: BattleScriptEmu._wait_for_proj_hit_hdlr, 
	BScriptOps.WaitForProjStop: BattleScriptEmu._wait_for_proj_stop_hdlr, 
	BScriptOps.SpawnUnitProjectile: BattleScriptEmu._spawn_unit_proj_hdlr, 
	BScriptOps.SetUnitFrame: BattleScriptEmu._set_unit_frame_hdlr,
	BScriptOps.WaitForFxScript: BattleScriptEmu._error_hdlr,
	BScriptOps.SetProjCounter: BattleScriptEmu._error_hdlr,  # Only used by Mage, Bishop
	BScriptOps.SetSpecialFrame: BattleScriptEmu._error_hdlr, # Only used by Mage
	BScriptOps.SetBgPalette: BattleScriptEmu._error_hdlr, # Never used?
	BScriptOps.PlaySound: BattleScriptEmu._nop_hdlr,
	BScriptOps.ShowFlockAnim: BattleScriptEmu._flock_anim_hdlr,
}

_op_fmts = {
	BScriptOps.SpawnAnimProjectile: "Spawn ANIMATED PROJECTILE {p:x} from active sprite",
	BScriptOps.SetCounter: "Set COUNTER to {p:x}",
	BScriptOps.BeginAnim: "BEGIN ANIMATION script {p:x} for active sprite",
	BScriptOps.FlipFacing: "FLIP active sprite horizontally",
	BScriptOps.PauseAnim: "PAUSE ANIMATION for active sprite",
	BScriptOps.ResumeAnim: "RESUME ANIMATION for active sprite",
	BScriptOps.ApplyDamage: "APPLY DAMAGE",
	BScriptOps.ShowHpBar: "SHOW HP BAR",
	BScriptOps.ShakeScreen: "SHAKE SCREEN",
	BScriptOps.SetXPos: "Set active sprite X POSITION to {p:x}",
	BScriptOps.SetFrame: "Set active sprite FRAME NUMBER to {p:x}",
	BScriptOps.SpawnProjectile: "Spawn UNANIMATED PROJECTILE {p:x} from active sprite",
	BScriptOps.WaitForProjFinish: "Pause until projectile MISSES",
	BScriptOps.WaitForProjHit: "Pause until projectile HITS ITS TARGET",
	BScriptOps.WaitForProjStop: "Pause until projectile STOPS MOVING",
	BScriptOps.SpawnUnitProjectile: "Spawn unit-specific projectile {p:x}",
	BScriptOps.SetUnitFrame: "Set UNIT-SPECIFIC FRAME {p} for active sprite",
	BScriptOps.WaitForFxScript: "SYNC with effect script",
	BScriptOps.SetProjCounter: "Set counter based on projectile",
	BScriptOps.SetSpecialFrame: "SET SPECIAL FRAME number {p:x} for active sprite",
	BScriptOps.SetBgPalette: "SET BACKGROUND PALETTE {p:x} for active sprite",
	BScriptOps.PlaySound: "PLAY SOUND {p:x}",
	BScriptOps.ShowFlockAnim: "Do FLOCK ANIMATION for 7 - counter ticks for active sprite",
}
_op_fmts = {key: fmt.format for key, fmt in _op_fmts.items()}
_op_fmts.update({
	BScriptOps.BeginMove: lambda o, p: f"{'BEGIN' if p & 0x80 else 'EXECUTE'} MOVEMENT script {p & 0x3f:x}{' mirrored' if p & 0x40 else ''} for active sprite",
	BScriptOps.WaitForCondition: lambda o, p: (f"WAIT COUNTER FRAMES" if p & 0x80 else f"Pause until ANIMATION FRAME {p:x} for active sprite"),
	BScriptOps.SetLayers: lambda o, p: f"SET LAYER for active sprite to {'background' if p & 2 else 'sprite'}, inactive sprite to {'background' if p & 1 else 'sprite'}",
	BScriptOps.LoadPacket: lambda o, p: f"LOAD PPU packet number {p:x}/{p ^ 2:x} for active sprite",
	BScriptOps.SpriteAttributes: lambda o, p: f"Set SPRITE ATTRIBS {p:x}: {'behind' if p & 0x20 else 'in front of'} background",
})

def _dump_battle_script(script, prefix, used_ops):
	for op_idx, op in enumerate(script):
		fmt = _op_fmts.get(op.opcode)
		if fmt:
			s = fmt(o = op.opcode, p = op.param)
		else:
			s = ""

		print(f"{op_idx:2x}: {op.opcode:02x} {op.param:02x}: {s}")

		used_ops[op.opcode] += 1

	print()
		
def dump_battle_scripts(data):
	battle_script_units = colls.defaultdict(
		functools.partial(colls.defaultdict, set))
	for unit_idx, script_idcs in enumerate(data.unit_battle_script_idcs):
		for anim_idx, script_idx in enumerate(script_idcs):
			battle_script_units[script_idx][unit_idx].add(anim_idx)

	battle_script_units = dict(sorted(battle_script_units.items()))

	used_ops = np.zeros((len(data.battle_scripts), 0x1d), dtype = int)
	for script_idx, script in enumerate(data.battle_scripts):
		script_units = battle_script_units.get(script_idx)
		unit_str = ""
		if script_units is not None:
			unit_strs = []
			for unit_idx in sorted(script_units.keys()):
				idcs_str = ", ".join(map(str, sorted(script_units[unit_idx])))
				unit_strs.append(
					f"{UnitTypes(unit_idx + 1).name} ({idcs_str})")

			unit_str = (": " + ", ".join(unit_strs)) if unit_strs else ""
				
		print(f"Battle Script {script_idx:x} @ {data.battle_script_addrs[script_idx]:4x}{unit_str}")

		_dump_battle_script(script, "\t", used_ops[script_idx])
		
	total_used_ops = used_ops.sum(axis = 0, dtype = int)
	script_nums = list(range(len(data.battle_scripts)))
	scripts_using_ops = [
		set(itertools.compress(script_nums, col))
		for col in used_ops.transpose()
	]

	return
