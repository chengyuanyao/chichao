"""Bounded match diagnostics and asynchronous, local-only JSON archives.

Client values are self-reported, never authoritative game data. No tokens,
addresses, chat, unit positions or browser storage are accepted by the schema.
"""
import copy
import json
import math
import os
import re
import threading
import time
from collections import OrderedDict

WRITER = None  # Enabled only by server.main; importing tests never writes files.
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SUM_FIELDS = ("frames", "ms", "over50", "over100", "loadSamples", "netMessages", "netGapSamples", "netGapMs",
              "netOver500", "stateBytes", "parseMs", "commandSamples", "commandMs", "commandFailures",
              "probeSamples", "probeMs", "probeFailures", "reconnects")
MAX_FIELDS = ("maxMs", "maxUnits", "maxDrawCalls", "maxTriangles", "maxParticles", "maxGeometries", "maxTextures",
              "netMaxGapMs", "parseMaxMs", "commandMaxMs", "probeMaxMs")


def numeric(value, limit=1e12):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= limit:
        raise ValueError("诊断数据包含无效数值")
    return value


def clean_row(value):
    if not isinstance(value, dict):
        raise ValueError("诊断数据格式无效")
    row = {k: numeric(value.get(k, 0)) for k in SUM_FIELDS + MAX_FIELDS}
    row["time"] = numeric(value.get("time", 0), 1e8)
    row["minScale"] = numeric(value.get("minScale", 1), 1)
    row["averageFps"] = 1000 * row["frames"] / row["ms"] if row["ms"] else 0
    return row


def sanitize(value):
    if not isinstance(value, dict) or not isinstance(value.get("clientRunId"), str) or not SAFE_ID.fullmatch(value["clientRunId"]):
        raise ValueError("无效的客户端诊断会话")
    periods = value.get("periods", [])
    if not isinstance(periods, list) or len(periods) > 120:
        raise ValueError("诊断时间段超过上限")
    result = clean_row(value)
    result.update(clientRunId=value["clientRunId"], sequence=numeric(value.get("sequence", 0)),
                  interval=numeric(value.get("interval", 30), 1e8), p95Ms=numeric(value.get("p95Ms", 0), 1001),
                  p95Overflow=value.get("p95Overflow") is True, full=value.get("full") is True,
                  periods=[clean_row(p) for p in periods])
    settings = value.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("无效的画面设置")
    result["settings"] = {k: str(settings[k])[:32] for k in ("shadows", "bloomQuality", "particleQuality", "width", "height") if k in settings}
    return result


def start(room):
    game = room["game"]
    game["_diagnostics"] = {"version": 1, "matchId": game["uid"], "roomId": room["id"],
                            "startedAt": time.time(), "players": [{"id": p["id"], "name": p["name"], "isBot": bool(p.get("isBot"))}
                            for p in room["players"].values()], "clients": {}, "server": {}, "periods": [], "interval": 30,
                            "_uploads": {}, "_lastArchive": 0, "_lastTick": None}
    game["_diagnostics"]["_terminalUploads"] = set()
    game["_diagnostics"]["_detailUploads"] = set()


def state(room):
    return (room.get("game") or {}).get("_diagnostics")


def _add(bucket, key, value):
    metric = bucket.get(key)
    if metric is None:
        metric = bucket[key] = {"count": 0, "sum": 0, "max": 0}
    metric["count"] += 1
    metric["sum"] += value
    metric["max"] = max(metric["max"], value)


def metric(room, key, value):
    data = state(room)
    if data is None:
        return
    _add(data["server"], key, value)
    stamp = room["game"].get("elapsed", 0)
    while stamp >= data["interval"] * 120:
        merged = []
        for i, row in enumerate(data["periods"]):
            if i % 2 == 0:
                merged.append(row)
            else:
                for name, src in row["metrics"].items():
                    dest = merged[-1]["metrics"].setdefault(name, {"count": 0, "sum": 0, "max": 0})
                    dest["count"] += src["count"]
                    dest["sum"] += src["sum"]
                    dest["max"] = max(dest["max"], src["max"])
        data["periods"] = merged
        data["interval"] *= 2
    index = int(stamp // data["interval"])
    while len(data["periods"]) <= index:
        data["periods"].append({"time": len(data["periods"]) * data["interval"], "metrics": {}})
    _add(data["periods"][index]["metrics"], key, value)


def accept(room, player, match_id, value, clock=None):
    data = state(room)
    if not data or match_id != data["matchId"] or player.get("isBot"):
        raise ValueError("诊断数据不属于当前对局")
    clock = time.monotonic() if clock is None else clock
    first_final = room.get("status") == "finished" and player["id"] not in data["_terminalUploads"]
    first_detail = isinstance(value, dict) and value.get("full") is True and player["id"] not in data["_detailUploads"]
    if not first_final and not first_detail and clock - data["_uploads"].get(player["id"], -1e20) < 2:
        raise ValueError("诊断上报过于频繁")
    clean = sanitize(value)
    if clean["full"]:
        data["_detailUploads"].add(player["id"])
        clean["detailReceivedAt"] = time.time()
    if room.get("status") == "finished":
        data["_terminalUploads"].add(player["id"])
    data["_uploads"][player["id"]] = clock
    entry = data["clients"].setdefault(player["id"], {"runs": [], "omittedRuns": 0})
    previous = next((r for r in entry["runs"] if r["clientRunId"] == clean["clientRunId"]), None)
    if previous and clean["sequence"] <= previous["sequence"]:
        return False
    if previous:
        if not clean["full"]:
            clean["periods"] = previous["periods"]
            clean["interval"] = previous["interval"]
            clean["detailReceivedAt"] = previous.get("detailReceivedAt")
        entry["runs"].remove(previous)
    elif len(entry["runs"]) >= 4:
        entry["runs"].pop(0)
        entry["omittedRuns"] += 1
    clean["receivedAt"] = time.time()
    clean["viewerId"] = player["id"]  # Identity never comes from the payload.
    clean["matchId"] = match_id
    entry["runs"].append(clean)
    if room.get("status") == "finished" or clean["full"]:
        queue_archive(room, force=True)
    return True


def transport(room, player_id, key, value):
    data = state(room)
    if data is not None:
        entry = data["clients"].setdefault(player_id, {"runs": [], "omittedRuns": 0})
        _add(entry.setdefault("transport", {}), key, value)


def snapshot(room, include_report=False, status=None, summary=False):
    data = state(room)
    if data is None:
        return None
    result = ({k: data[k] for k in ("matchId", "startedAt")} if summary else
              copy.deepcopy({k: v for k, v in data.items() if not k.startswith("_") and k != "clients"}))
    if not summary:
        # Accepted run records are immutable: replacement never edits an old run.
        # Copy containers only, avoiding thousands of historical rows under the sim lock.
        result["clients"] = {pid: {"runs": list(entry["runs"]), "omittedRuns": entry["omittedRuns"],
                                    "transport": copy.deepcopy(entry.get("transport", {}))}
                             for pid, entry in data["clients"].items()}
    report = (room.get("game") or {}).get("_battleReport", {})
    result.update(status=status or room.get("status"), elapsed=room["game"].get("elapsed", 0),
                  mapName=report.get("mapName", ""), savedAt=time.time())
    if include_report:
        if report.get("finished"):
            result["report"] = copy.deepcopy(report["public"])
        else:
            # Partial archive is explicitly labelled, never presented as a final result.
            keys = ("version", "matchId", "mapName", "mapId", "firstCombatAt", "samples", "events", "droppedEvents",
                    "sampleInterval", "phases", "phaseSeconds", "engagements", "omittedEngagements")
            partial = {k: copy.deepcopy(report[k]) for k in keys if k in report}
            partial.update(duration=result["elapsed"], incomplete=True,
                           players=[copy.deepcopy({k: v for k, v in p.items() if not k.startswith("_")})
                                    for p in report.get("players", {}).values()])
            result["report"] = partial
    return result


def queue_archive(room, force=False, status=None):
    data = state(room)
    if WRITER is None or data is None:
        return
    clock = time.monotonic()
    if not force and clock - data["_lastArchive"] < 60:
        return
    data["_lastArchive"] = clock
    WRITER.submit(snapshot(room, include_report=force and (room.get("status") == "finished" or status is not None), status=status))


class ArchiveWriter:
    """Coalescing bounded queue; serialization and disk I/O never run on sim ticks."""
    def __init__(self, directory, max_bytes=512 * 1024 * 1024):
        self.directory = os.path.abspath(directory)
        self.max_bytes = max_bytes
        self.pending = OrderedDict()
        self.index = {}
        self.error = None
        self.errors = {}
        self.condition = threading.Condition()
        self.stopping = False
        self.worker = threading.Thread(target=self._run, name="report-archive", daemon=True)
        self.worker.start()

    def submit(self, document):
        with self.condition:
            key = document["matchId"]
            if key not in self.pending and len(self.pending) >= 64:
                self.error = "战报写入队列已满，部分自动保存未完成"
                return
            self.pending[key] = document
            self.condition.notify()

    def _path(self, match_id):
        if not SAFE_ID.fullmatch(str(match_id)):
            raise ValueError("无效的战报编号")
        return os.path.join(self.directory, match_id + ".json")

    def read(self, match_id):
        path = self._path(match_id)
        if os.path.getsize(path) > 4 * 1024 * 1024:
            raise ValueError("战报文件超过读取上限")
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)

    def _remember(self, document):
        row = {k: document.get(k) for k in ("matchId", "mapName", "status", "elapsed", "startedAt", "savedAt")}
        with self.condition:
            self.index[row["matchId"]] = row
            if len(self.index) > 200:
                oldest = min(self.index, key=lambda k: self.index[k].get("savedAt") or 0)
                del self.index[oldest]  # Only evict the UI index. Never delete user archives.

    def history(self):
        with self.condition:
            return {"archives": sorted(self.index.values(), key=lambda r: r.get("savedAt") or 0, reverse=True),
                    "archiveError": self.error or "; ".join(sorted(set(self.errors.values()))) or None,
                    "pending": len(self.pending), "directory": self.directory}

    def _run(self):
        try:
            os.makedirs(self.directory, exist_ok=True)
            paths = [os.path.join(self.directory, name) for name in os.listdir(self.directory) if name.endswith(".json")]
            total = sum(os.path.getsize(p) for p in paths)
            for path in sorted(paths, key=os.path.getmtime, reverse=True)[:200]:
                try:
                    self._remember(self.read(os.path.basename(path)[:-5]))
                except (OSError, ValueError, KeyError, TypeError):
                    pass
        except OSError as exc:
            total = 0
            self.error = "无法初始化战报目录：" + str(exc)
        while True:
            with self.condition:
                while not self.pending and not self.stopping:
                    self.condition.wait()
                if not self.pending:
                    return
                key, document = self.pending.popitem(last=False)
            try:
                path = self._path(key)
                raw = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
                old_size = os.path.getsize(path) if os.path.exists(path) else 0
                if len(raw) > 4 * 1024 * 1024 or total - old_size + len(raw) > self.max_bytes:
                    raise ValueError("战报存储达到容量上限；请备份并清理目录，不会自动删除历史")
                with open(path + ".tmp", "wb") as stream:
                    stream.write(raw)
                os.replace(path + ".tmp", path)
                total += len(raw) - old_size
                self._remember(document)
                with self.condition:
                    self.errors.pop(key, None)
            except (OSError, ValueError, TypeError) as exc:
                with self.condition:
                    if len(self.errors) < 64 or key in self.errors:
                        self.errors[key] = "战报保存失败：" + str(exc)
                    else:
                        self.error = "多场战报保存失败，请检查存储目录"

    def close(self):
        with self.condition:
            self.stopping = True
            self.condition.notify()
        self.worker.join(5)
