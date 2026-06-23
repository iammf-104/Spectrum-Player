import json
import os
import re
import shutil
import sys
import unicodedata
import uuid
from pathlib import Path


def find_file_by_name(original_path, max_depth=3):
    """Try to locate a moved/renamed file by searching near its old location
    and common user directories.  Returns the new absolute path, or None."""
    filename = os.path.basename(original_path)
    if not filename:
        return None
    old_dir = os.path.dirname(os.path.abspath(original_path))

    search_dirs = []
    # 1. Same folder and its parent (files often just moved up/down one level)
    search_dirs.append(old_dir)
    parent = os.path.dirname(old_dir)
    if parent and parent != old_dir:
        search_dirs.append(parent)

    # 2. Common user music/download folders
    home = os.path.expanduser('~')
    for rel in ('Music', '音乐', 'Desktop', '桌面', 'Downloads', '下载', 'Documents'):
        p = os.path.join(home, rel)
        if os.path.isdir(p):
            search_dirs.append(p)

    seen = set()
    for base in search_dirs:
        base = os.path.normcase(os.path.abspath(base))
        if base in seen or not os.path.isdir(base):
            continue
        seen.add(base)
        for root, dirs, files in os.walk(base):
            if filename in files:
                candidate = os.path.normpath(os.path.join(root, filename))
                if os.path.isfile(candidate):
                    return candidate
            # Limit recursion depth
            depth = len(os.path.relpath(root, base).split(os.sep))
            if depth >= max_depth:
                dirs.clear()

    return None


def _app_base_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def _parse_num(value, default=0):
    if value is None:
        return default
    s = str(value).strip()
    if not s:
        return default
    m = re.match(r'(\d+)', s)
    return int(m.group(1)) if m else default


_ARTIST_SPLIT = re.compile(
    r'\s*(?:/|;|,|、|，|&|\+|\band\b|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b|\bvs\.?\b)\s*',
    re.IGNORECASE,
)


def parse_artists(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(parse_artists(item))
        return _unique_artists(out)
    text = str(value).strip()
    if not text:
        return []
    parts = [p.strip() for p in _ARTIST_SPLIT.split(text) if p.strip()]
    return _unique_artists(parts if parts else [text])


def _unique_artists(names):
    seen = set()
    out = []
    for name in names:
        n = str(name).strip()
        if not n:
            continue
        key = n.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def _read_artists_from_tags(audio):
    artists = []
    tags = getattr(audio, 'tags', None)
    if tags is None:
        return artists
    if hasattr(tags, 'getall'):
        for key in ('artist', 'TPE1', 'ARTIST'):
            try:
                for val in tags.getall(key):
                    artists.extend(parse_artists(str(val)))
            except Exception:
                pass
    if not artists:
        for key in ('artist', 'ARTIST'):
            try:
                val = tags.get(key)
            except Exception:
                val = None
            if val:
                if isinstance(val, (list, tuple)):
                    for item in val:
                        artists.extend(parse_artists(item))
                else:
                    artists.extend(parse_artists(val))
    return _unique_artists(artists)


def _read_albumartist(tags, audio):
    if tags is None:
        return ''
    if hasattr(tags, 'getall'):
        for key in ('albumartist', 'ALBUMARTIST', 'TPE2'):
            try:
                vals = tags.getall(key)
            except Exception:
                vals = None
            if vals:
                return str(vals[0]).strip()
    for key in ('albumartist', 'ALBUMARTIST', 'TPE2'):
        try:
            val = tags.get(key)
        except Exception:
            val = None
        if val:
            if isinstance(val, (list, tuple)):
                return str(val[0]).strip() if val else ''
            return str(val).strip()
    return ''


def read_track_metadata(path):
    path = os.path.normpath(os.path.abspath(path))
    base = os.path.splitext(os.path.basename(path))[0]
    meta = {
        'path': path,
        'title': base,
        'artist': '',
        'album': '',
        'albumartist': '',
        'artists': [],
        'track_num': 0,
        'disc_num': 0,
    }
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(path, easy=True)
        if audio is None or not audio.tags:
            return meta
        tags = audio.tags

        def _tag(name, default=''):
            v = tags.get(name)
            if not v:
                return default
            if isinstance(v, (list, tuple)):
                return str(v[0]) if v else default
            return str(v)

        meta['title'] = _tag('title', base)
        meta['artist'] = _tag('artist')
        meta['album'] = _tag('album')
        meta['albumartist'] = _read_albumartist(tags, audio)
        meta['artists'] = _read_artists_from_tags(audio)
        if not meta['artists'] and meta['artist']:
            meta['artists'] = parse_artists(meta['artist'])
        meta['track_num'] = _parse_num(_tag('tracknumber', '0'))
        meta['disc_num'] = _parse_num(_tag('discnumber', '0'))
    except Exception:
        pass
    return meta


class PlaylistStore:
    def __init__(self, path=None):
        if path is None:
            path = _app_base_dir() / 'playlists.json'
        self.path = Path(path)
        self.library_dir = self.path.parent / 'music_library'
        self.data = {
            'playlists': [],
            'active_playlist_id': None,
            'track_index': 0,
        }
        self.load()

    def load(self):
        loaded = False
        # Try primary file, then fall back to .bak if primary is corrupted.
        for candidate in (self.path, self.path.with_suffix('.bak')):
            if not candidate.exists():
                continue
            try:
                with open(candidate, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    self.data.update(raw)
                loaded = True
                break
            except Exception as e:
                self._write_log(f'Playlist load error ({candidate.name}): {e}')
                print(f'Playlist load error ({candidate.name}):', e)

        if not loaded:
            self.save()   # create empty file
            return

        try:
            self._repair_playlists()
        except Exception as e:
            self._write_log(f'Repair error: {e}')

        # Migration runs in its own try/except so a failure here never
        # prevents the playlists from being used.
        try:
            self._migrate_existing_to_library()
        except Exception as e:
            self._write_log(f'Migration error: {e}')
            print('Migration error:', e)

    def _migrate_existing_to_library(self):
        """On first run after library feature was added, copy all existing
        tracks that live outside music_library/ into it and update their paths."""
        lib = os.path.normpath(os.path.abspath(str(self.library_dir)))
        changed = False
        # Collect unique paths that need migration
        for pl in self.data.get('playlists', []):
            for track in pl.get('tracks', []):
                old_path = track.get('path') or ''
                if not old_path or not os.path.isfile(old_path):
                    continue
                norm = os.path.normpath(os.path.abspath(old_path))
                # Already inside library — skip
                try:
                    if os.path.commonpath([norm, lib]) == lib:
                        continue
                except ValueError:
                    pass  # different drives on Windows
                new_path = self._copy_to_library(old_path)
                if new_path and new_path != old_path:
                    track['path'] = new_path
                    changed = True
        if changed:
            self.save()
            print(f'已将现有歌曲迁移到音乐库：{lib}')

    def _strip_kind_prefix(self, name):
        n = (name or '').strip()
        while True:
            cleaned = re.sub(r'^\[(歌手|专辑)\]\s*', '', n)
            if cleaned == n:
                break
            n = cleaned
        return n

    def _repair_playlists(self):
        for pl in self.data.get('playlists', []):
            pl['name'] = self._strip_kind_prefix(pl.get('name', ''))
            if pl.get('kind') == 'album':
                norm = self._album_name_from_key(pl.get('album_key'))
                if not norm and pl.get('tracks'):
                    norm = self._norm_album(pl['tracks'][0].get('album'))
                if norm:
                    pl['album_key'] = ['album', norm]
                    if not pl.get('name'):
                        pl['name'] = pl['tracks'][0].get('album') or norm
        self.consolidate_album_playlists(save=False)
        self.ensure_queue_playlist()
        self.save()

    QUEUE_NAME = '播放列表'

    def ensure_queue_playlist(self):
        for pl in self.data.get('playlists', []):
            if pl.get('kind') == 'queue':
                pl['name'] = self.QUEUE_NAME
                return pl
        return self.create_playlist(self.QUEUE_NAME, kind='queue')

    def list_manual_playlists(self):
        return [p for p in self.data.get('playlists', []) if p.get('kind') == 'manual']

    def list_album_playlists(self):
        return [p for p in self.data.get('playlists', []) if p.get('kind') == 'album']

    def list_artist_playlists(self):
        return [p for p in self.data.get('playlists', []) if p.get('kind') == 'artist']

    def consolidate_album_playlists(self, save=True):
        groups = {}
        for pl in self.data.get('playlists', []):
            if pl.get('kind') != 'album':
                continue
            norm = self._album_name_from_key(pl.get('album_key'))
            if not norm and pl.get('tracks'):
                norm = self._norm_album(pl['tracks'][0].get('album'))
            if not norm:
                continue
            groups.setdefault(norm, []).append(pl)

        changed = False
        for norm, pls in groups.items():
            if len(pls) < 2:
                if pls[0].get('album_key') != ['album', norm]:
                    pls[0]['album_key'] = ['album', norm]
                    changed = True
                continue
            master = pls[0]
            paths = {t.get('path') for t in master.get('tracks', [])}
            for other in pls[1:]:
                for t in other.get('tracks', []):
                    if t.get('path') not in paths:
                        master.setdefault('tracks', []).append(t)
                        paths.add(t.get('path'))
                if other.get('id') == self.data.get('active_playlist_id'):
                    self.data['active_playlist_id'] = master.get('id')
                self.data['playlists'] = [
                    p for p in self.data['playlists'] if p.get('id') != other.get('id')]
                changed = True
            master['album_key'] = ['album', norm]
            master['name'] = self._album_playlist_name_from_tracks(master.get('tracks', []), norm)
            self.sort_album_tracks(master)
            changed = True
        if changed and save:
            self.save()
    def _copy_to_library(self, src_path):
        """Copy src_path into music_library/ and return the new path.

        Rules:
        - If the file is already inside music_library/, return it unchanged.
        - If a file with the same name already exists and is identical (same
          size), reuse the existing copy to avoid duplicates.
        - If a same-named but different file exists, append _2, _3 … until
          a free name is found.
        Returns the absolute destination path, or src_path on any error.
        """
        try:
            src = os.path.normpath(os.path.abspath(src_path))
            lib = os.path.normpath(os.path.abspath(str(self.library_dir)))
            # Already inside the library — nothing to do
            try:
                if os.path.commonpath([src, lib]) == lib:
                    return src
            except ValueError:
                pass  # different drives on Windows — file is definitely not in library
            self.library_dir.mkdir(parents=True, exist_ok=True)
            filename = os.path.basename(src)
            stem, ext = os.path.splitext(filename)
            dst = os.path.join(lib, filename)
            counter = 2
            while os.path.exists(dst):
                if os.path.getsize(dst) == os.path.getsize(src):
                    # Same size → treat as identical, reuse
                    return os.path.normpath(dst)
                dst = os.path.join(lib, f'{stem}_{counter}{ext}')
                counter += 1
            shutil.copy2(src, dst)
            return os.path.normpath(dst)
        except Exception as e:
            print(f'Library copy error ({src_path}):', e)
            return src_path

    def _write_log(self, msg):
        """Append msg to player_errors.log (visible even in --windowed exe)."""
        try:
            import datetime
            log_path = self.path.parent / 'player_errors.log'
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f'[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n')
        except Exception:
            pass

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: write to .tmp then rename, so a crash mid-write
            # never leaves a corrupted playlists.json.
            tmp = self.path.with_suffix('.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            # Keep one .bak of the last known-good file before overwriting.
            if self.path.exists():
                try:
                    self.path.replace(self.path.with_suffix('.bak'))
                except Exception:
                    pass
            tmp.replace(self.path)
        except Exception as e:
            self._write_log(f'Playlist save error: {e}')
            print('Playlist save error:', e)

    def _new_id(self):
        return uuid.uuid4().hex[:12]

    def list_playlists(self):
        return self.data['playlists']

    def get_playlist(self, playlist_id):
        for pl in self.data['playlists']:
            if pl.get('id') == playlist_id:
                return pl
        return None

    def get_active_playlist(self):
        pid = self.data.get('active_playlist_id')
        if not pid:
            return None
        return self.get_playlist(pid)

    def set_active(self, playlist_id, track_index=0):
        self.data['active_playlist_id'] = playlist_id
        pl = self.get_playlist(playlist_id)
        if pl and pl.get('tracks'):
            track_index = max(0, min(track_index, len(pl['tracks']) - 1))
        else:
            track_index = 0
        self.data['track_index'] = track_index
        self.save()

    def get_track_index(self):
        return int(self.data.get('track_index', 0))

    def set_track_index(self, index):
        self.data['track_index'] = max(0, int(index))
        self.save()

    def create_playlist(self, name, kind='manual', album_key=None, artist_key=None):
        pl = {
            'id': self._new_id(),
            'name': name.strip() or '未命名歌单',
            'kind': kind,
            'album_key': album_key,
            'artist_key': artist_key,
            'tracks': [],
        }
        self.data['playlists'].append(pl)
        self.save()
        return pl

    def delete_playlist(self, playlist_id):
        pl = self.get_playlist(playlist_id)
        if pl is None:
            return
        kind = pl.get('kind')
        if kind == 'queue':
            pl['tracks'] = []
            self.save()
            return
        if kind == 'artist':
            # Artist playlists are auto-managed; they cannot be deleted manually.
            return
        self.data['playlists'] = [
            p for p in self.data['playlists'] if p.get('id') != playlist_id]
        if self.data.get('active_playlist_id') == playlist_id:
            self.data['active_playlist_id'] = None
            self.data['track_index'] = 0
        if kind == 'album':
            # Rebuild artist playlists so they reflect the remaining albums.
            self.rebuild_artist_playlists()
        else:
            self.save()

    def rebuild_artist_playlists(self):
        """Discard all artist playlists and recreate them from album tracks."""
        self.data['playlists'] = [
            p for p in self.data['playlists'] if p.get('kind') != 'artist']
        for pl in list(self.data['playlists']):
            if pl.get('kind') != 'album':
                continue
            for track in pl.get('tracks', []):
                self.sync_artists_for_track(track)
        self.save()

    def _norm_album(self, name):
        s = unicodedata.normalize('NFKC', (name or '').strip())
        s = re.sub(r'\s+', ' ', s)
        return s.casefold()

    def _album_playlist_name_from_tracks(self, tracks, norm_album):
        aa = ''
        for t in tracks:
            candidate = (t.get('albumartist') or '').strip()
            if candidate and '/' not in candidate and ';' not in candidate:
                aa = candidate
                break
        display_album = ''
        for t in tracks:
            if self._norm_album(t.get('album')) == norm_album:
                display_album = (t.get('album') or '').strip()
                break
        display_album = display_album or norm_album
        if aa:
            return f'{aa} - {display_album}'
        return display_album

    def _album_playlist_name(self, meta):
        norm = self._norm_album(meta.get('album'))
        if not norm:
            return '未知专辑'
        aa = (meta.get('albumartist') or '').strip()
        album = (meta.get('album') or '').strip() or norm
        if aa and '/' not in aa and ';' not in aa:
            return f'{aa} - {album}'
        return album

    def _album_key(self, meta):
        album = self._norm_album(meta.get('album'))
        if not album:
            return None
        return ['album', album]

    def _album_name_from_key(self, key):
        if not key or not isinstance(key, list):
            return None
        if len(key) >= 2 and key[0] == 'album':
            return key[1]
        if len(key) >= 3 and key[0] == 'aa':
            return key[2]
        if len(key) >= 2 and isinstance(key[1], str):
            return self._norm_album(key[1])
        return None

    def find_album_playlist(self, meta):
        norm_album = self._norm_album(meta.get('album'))
        if not norm_album:
            return None
        for pl in self.data['playlists']:
            if pl.get('kind') != 'album':
                continue
            if self._album_name_from_key(pl.get('album_key')) == norm_album:
                return pl
            for t in pl.get('tracks', []):
                if self._norm_album(t.get('album')) == norm_album:
                    return pl
        return None
    @staticmethod
    def sort_album_tracks(pl):
        pl['tracks'].sort(key=lambda t: (
            int(t.get('disc_num', 0) or 0),
            int(t.get('track_num', 0) or 0),
            str(t.get('title', '')).lower(),
        ))

    def sync_album_playlist(self, meta):
        album = (meta.get('album') or '').strip()
        if not album:
            return None
        pl = self.find_album_playlist(meta)
        if pl is None:
            pl = self.create_playlist(
                self._album_playlist_name(meta),
                kind='album',
                album_key=self._album_key(meta),
            )
        else:
            pl['album_key'] = self._album_key(meta)
            pl['name'] = self._album_playlist_name_from_tracks(
                pl.get('tracks', []) + [meta], self._norm_album(meta.get('album')))
        paths = {t.get('path') for t in pl.get('tracks', [])}
        if meta['path'] not in paths:
            pl['tracks'].append(dict(meta))
        self.sort_album_tracks(pl)
        self.save()
        return pl

    def find_artist_playlist(self, artist_name):
        name = (artist_name or '').strip()
        if not name:
            return None
        key = name.casefold()
        for pl in self.data['playlists']:
            if pl.get('kind') != 'artist':
                continue
            ak = pl.get('artist_key') or []
            if ak and str(ak[0]).strip().casefold() == key:
                return pl
            if self._strip_kind_prefix(pl.get('name', '')).casefold() == key:
                return pl
        return None
    @staticmethod
    def sort_artist_tracks(pl):
        pl['tracks'].sort(key=lambda t: (
            str(t.get('album', '')).lower(),
            int(t.get('disc_num', 0) or 0),
            int(t.get('track_num', 0) or 0),
            str(t.get('title', '')).lower(),
        ))

    def sync_artist_playlist(self, meta, artist_name):
        name = (artist_name or '').strip()
        if not name:
            return None
        pl = self.find_artist_playlist(name)
        if pl is None:
            pl = self.create_playlist(
                name,
                kind='artist',
                artist_key=[name],
            )
        paths = {t.get('path') for t in pl.get('tracks', [])}
        if meta['path'] not in paths:
            pl['tracks'].append(dict(meta))
        self.sort_artist_tracks(pl)
        self.save()
        return pl

    def sync_artists_for_track(self, meta):
        artists = list(meta.get('artists') or [])
        if not artists:
            raw = (meta.get('artist') or meta.get('albumartist') or '').strip()
            artists = parse_artists(raw) if raw else []
        if not artists:
            artists = ['未知艺术家']
        synced = []
        for artist in artists:
            pl = self.sync_artist_playlist(meta, artist)
            if pl:
                synced.append(pl)
        return synced

    def import_dropped_files(self, file_paths):
        added = []
        album_names = set()
        artist_names = set()
        for fp in file_paths:
            meta = read_track_metadata(fp)
            if not os.path.isfile(meta['path']):
                continue
            # Copy to local library so the path never breaks
            lib_path = self._copy_to_library(meta['path'])
            if lib_path != meta['path']:
                meta = read_track_metadata(lib_path)   # re-read from library copy
            alb = self.sync_album_playlist(meta)
            if alb:
                album_names.add(alb.get('name', ''))
            for pl in self.sync_artists_for_track(meta):
                artist_names.add(pl.get('name', ''))
            added.append(meta)
        self.consolidate_album_playlists()
        self.save()
        return {
            'added': added,
            'albums': sorted(album_names),
            'artists': sorted(artist_names),
        }

    def replace_queue_from(self, source_pl_id):
        """Copy all tracks from another playlist into the play queue."""
        q = self.ensure_queue_playlist()
        src = self.get_playlist(source_pl_id)
        if not src or not src.get('tracks'):
            q['tracks'] = []
        else:
            q['tracks'] = [dict(t) for t in src['tracks']]
        self.save()
        return q

    def get_queue_playlist(self):
        return self.ensure_queue_playlist()

    def add_tracks_to_playlist(self, playlist_id, file_paths, sync_albums=True):
        pl = self.get_playlist(playlist_id)
        if pl is None:
            return []
        added = []
        existing = {t.get('path') for t in pl.get('tracks', [])}
        for fp in file_paths:
            meta = read_track_metadata(fp)
            if not os.path.isfile(meta['path']):
                continue
            # Copy to local library
            lib_path = self._copy_to_library(meta['path'])
            if lib_path != meta['path']:
                meta = read_track_metadata(lib_path)
            if sync_albums:
                self.sync_album_playlist(meta)
                self.sync_artists_for_track(meta)
            if meta['path'] in existing:
                continue
            pl['tracks'].append(dict(meta))
            existing.add(meta['path'])
            added.append(meta)
        if pl.get('kind') == 'album':
            self.sort_album_tracks(pl)
        self.save()
        return added

    def add_track_ref(self, playlist_id, track):
        pl = self.get_playlist(playlist_id)
        if pl is None:
            return False
        path = track.get('path')
        if not path:
            return False
        if any(t.get('path') == path for t in pl.get('tracks', [])):
            return False
        pl['tracks'].append(dict(track))
        self.save()
        return True

    def add_to_queue(self, track_or_meta):
        q = self.ensure_queue_playlist()
        if isinstance(track_or_meta, str):
            meta = read_track_metadata(track_or_meta)
            if not os.path.isfile(meta['path']):
                return False
            self.sync_album_playlist(meta)
            self.sync_artists_for_track(meta)
            return self.add_track_ref(q['id'], meta)
        return self.add_track_ref(q['id'], track_or_meta)

    def move_track_to_index(self, playlist_id, from_idx, to_idx):
        pl = self.get_playlist(playlist_id)
        if pl is None or pl.get('kind') in ('album', 'artist'):
            return False
        tracks = pl.get('tracks', [])
        if not (0 <= from_idx < len(tracks)):
            return False
        to_idx = max(0, min(int(to_idx), len(tracks) - 1))
        if from_idx == to_idx:
            return True
        item = tracks.pop(from_idx)
        tracks.insert(to_idx, item)
        self.save()
        return True

    def move_track_to_playlist(self, from_pl_id, from_idx, to_pl_id, to_idx):
        """Move or copy a track into manual/queue playlist at to_idx."""
        from_pl = self.get_playlist(from_pl_id)
        to_pl = self.get_playlist(to_pl_id)
        if not from_pl or not to_pl or to_pl.get('kind') not in ('manual', 'queue'):
            return False
        if from_pl_id == to_pl_id:
            return self.move_track_to_index(from_pl_id, from_idx, to_idx)

        if not (0 <= from_idx < len(from_pl.get('tracks', []))):
            return False
        track = dict(from_pl['tracks'][from_idx])
        path = track.get('path')
        if not path:
            return False

        if from_pl.get('kind') in ('manual', 'queue'):
            from_pl['tracks'].pop(from_idx)

        to_tracks = [t for t in to_pl.get('tracks', []) if t.get('path') != path]
        to_idx = max(0, min(int(to_idx), len(to_tracks)))
        to_tracks.insert(to_idx, track)
        to_pl['tracks'] = to_tracks
        self.save()
        return True

    def _remove_path_from_auto_playlists(self, path, except_pl_id=None):
        """Remove a file path from all album/artist playlists except one already updated."""
        if not path:
            return
        for pl in self.data['playlists']:
            if pl.get('kind') not in ('album', 'artist'):
                continue
            if pl.get('id') == except_pl_id:
                continue
            pl['tracks'] = [t for t in pl.get('tracks', []) if t.get('path') != path]

    def remove_track(self, playlist_id, index, *, sync_auto_playlists=False):
        pl = self.get_playlist(playlist_id)
        if pl is None:
            return None
        tracks = pl.get('tracks', [])
        if not (0 <= index < len(tracks)):
            return None
        track = tracks.pop(index)
        path = track.get('path')
        if sync_auto_playlists and path and pl.get('kind') in ('album', 'artist'):
            self._remove_path_from_auto_playlists(path, except_pl_id=playlist_id)
        self.save()
        return track

    def move_track(self, playlist_id, index, direction):
        pl = self.get_playlist(playlist_id)
        if pl is None or pl.get('kind') in ('album', 'artist'):
            return False
        tracks = pl.get('tracks', [])
        j = index + direction
        if index < 0 or index >= len(tracks) or j < 0 or j >= len(tracks):
            return False
        tracks[index], tracks[j] = tracks[j], tracks[index]
        self.save()
        return True

    def track_at(self, playlist_id, index):
        pl = self.get_playlist(playlist_id)
        if not pl:
            return None
        tracks = pl.get('tracks', [])
        if 0 <= index < len(tracks):
            return tracks[index]
        return None

    def has_next(self, playlist_id=None, index=None):
        pl = self.get_playlist(playlist_id) if playlist_id else self.get_active_playlist()
        if not pl:
            return False
        idx = self.get_track_index() if index is None else index
        return idx + 1 < len(pl.get('tracks', []))

    def update_track_path(self, old_path, new_path):
        """Replace every occurrence of old_path with new_path across all playlists."""
        old_norm = os.path.normcase(os.path.normpath(os.path.abspath(old_path)))
        new_abs  = os.path.normpath(os.path.abspath(new_path))
        changed = False
        for pl in self.data.get('playlists', []):
            for track in pl.get('tracks', []):
                tp = track.get('path') or ''
                if os.path.normcase(os.path.normpath(os.path.abspath(tp))) == old_norm:
                    track['path'] = new_abs
                    changed = True
        if changed:
            self.save()
        return changed
