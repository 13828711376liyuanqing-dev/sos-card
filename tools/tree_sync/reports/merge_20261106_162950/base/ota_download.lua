-- SAM | 2026-10-30 08:58 +08:00 | Resumable candidate download into a file with periodic checkpoints (manager:save_download).
local candidate_paths=require("ota_candidates")
local M = {}
local HARD_LIMIT, CHUNK_LIMIT = 16 * 1024 * 1024, 16 * 1024

local function integer(n, lo, hi)
    return type(n) == "number" and n == math.floor(n) and n >= lo and n <= hi
end
local function hex(s, n)
    return type(s) == "string" and #s == n and s:match("^[0-9a-fA-F]+$") ~= nil
end
local function etag(s)
    return type(s) == "string" and #s >= 2 and #s <= 256
        and s:match('^"[^"%c]*"$') ~= nil
end
local function copy(t)
    local out = {}
    for k, v in pairs(t or {}) do out[k] = v end
    return out
end
local function header(headers, name)
    local found
    for k, v in pairs(headers) do
        if type(k) == "string" and k:lower() == name then
            if found ~= nil or type(v) ~= "string" then return nil end
            found = v
        end
    end
    return found
end

function M.new(port)
    port = port or {}
    local self = {state = "IDLE", offset = 0}
    local job, path, entity, durable, busy, paused
    local max_size = port.max_size or HARD_LIMIT
    local chunk_size = port.chunk_size or 4096
    local function fail(reason)
        self.error = reason
        self.state = paused and "PAUSED" or "ERROR"
        return false, reason
    end
    local function call(name, ...)
        if type(port[name]) ~= "function" then return nil end
        local ok, value, reason = pcall(port[name], ...)
        if name=="http_get" then
            local codes={BUSINESS_PAUSED="paused",HTTP_BUSY="paused",NETWORK_ERROR="network_error",
                HTTP_TIMEOUT="network_timeout",HTTP_IDLE_TIMEOUT="network_idle_timeout",HTTP_EOF="network_eof",HTTP_SOCKET="network_socket",
                GR_OWNERSHIP_LOST="ownership_lost",BUNDLE_ENTITY_CHANGED="entity_changed",
                HTTP_RANGE_REQUIRED="restart_required",HTTP_LENGTH="body_length",
                HTTP_CONTENT_RANGE="content_range",HTTP_ETAG="entity_changed",HTTP_REDIRECT="redirect"}
            local code=codes[ok and reason or value]
            if ok then return value,code end
            return nil,code
        end
        if ok then return value end
        return nil -- Do not leak authenticated URLs or credentials in errors.
    end
    local function record(offset, tag)
        return {offset = offset, etag = tag, sha256 = job.sha256,
            md5 = job.md5, size = job.size, path = path}
    end
    function self:status()
        return {state = self.state, offset = self.offset, path = path, etag = entity,
            error = self.error, checkpoint = durable and copy(durable) or nil}
    end
    function self:start(input, checkpoint)
        if busy then return false, "busy" end
        if not integer(max_size, 1, HARD_LIMIT) or not integer(chunk_size, 1, CHUNK_LIMIT)
            or type(input) ~= "table" or not integer(input.size, 1, max_size)
            or not hex(input.sha256, 64) or not hex(input.md5, 32)
            or type(input.url) ~= "string" or #input.url > 2048
            or input.url:find("[%c%s]") or input.url:find("#", 1, true)
            or not input.url:match("^https?://[^/%?#]+") then
            return false, "invalid_job"
        end
        local candidate = candidate_paths.path(input.sha256)
        local offset, tag = 0, nil
        if checkpoint ~= nil then
            if type(checkpoint) ~= "table" or checkpoint.sha256 ~= input.sha256:lower()
                or checkpoint.size ~= input.size or checkpoint.md5 ~= input.md5:lower()
                or checkpoint.path ~= candidate or not integer(checkpoint.offset, 0, input.size)
                or (checkpoint.offset > 0 and not etag(checkpoint.etag))
                or (checkpoint.etag ~= nil and not etag(checkpoint.etag)) then
                return false, "invalid_checkpoint"
            end
            offset, tag = checkpoint.offset, checkpoint.etag
        end
        for _, name in ipairs({"size", "truncate", "write", "read", "http_get", "checkpoint"}) do
            if type(port[name]) ~= "function" then return false, "capability_unavailable" end
        end
        local actual = call("size", candidate)
        if not integer(actual, offset, HARD_LIMIT) then return false, "candidate_missing_or_short" end
        -- Only our hash-derived candidate can be truncated. No caller path is used.
        if actual ~= offset and call("truncate", candidate, offset) ~= true then
            return false, "truncate_failed"
        end
        job = copy(input)
        job.sha256, job.md5 = input.sha256:lower(), input.md5:lower()
        path, entity, paused, self.offset = candidate, tag, false, offset
        durable, self.error = record(offset, tag), nil
        self.state = offset == job.size and "DOWNLOADED" or "DOWNLOADING"
        return true
    end
    function self:pause()
        paused = true
        if self.state ~= "VERIFIED" then self.state = "PAUSED" end
        return true
    end
    function self:step()
        if busy then return false, "busy" end
        if paused then return false, "paused" end
        if self.state ~= "DOWNLOADING" then return false, "not_downloading" end
        busy = true
        local first = self.offset
        local last = math.min(first + chunk_size, job.size) - 1
        local count = last - first + 1
        local headers = {Range = "bytes=" .. first .. "-" .. last}
        if entity then headers["If-Range"] = entity end
        local r, transport_reason = call("http_get", job.url, headers, count)
        busy = false
        if paused then return false, "paused" end -- Discard a late network response.
        if type(r) ~= "table" then return fail(transport_reason or "network_error") end
        if r.status == 200 then return fail("restart_required") end
        if r.status ~= 206 or type(r.headers) ~= "table" then return fail("http_status") end
        local range = header(r.headers, "content-range")
        local a, b, total
        if range then a, b, total = range:match("^bytes (%d+)%-(%d+)/(%d+)$") end
        if tonumber(a) ~= first or tonumber(b) ~= last or tonumber(total) ~= job.size then
            return fail("content_range")
        end
        local length = header(r.headers, "content-length")
        if not length or not length:match("^%d+$") or tonumber(length) ~= count
            or type(r.body) ~= "string" or #r.body ~= count then return fail("body_length") end
        local next_entity = header(r.headers, "etag")
        if not etag(next_entity) or (entity and entity ~= next_entity) then return fail("entity_changed") end
        -- Serialize write/readback/checkpoint even if a target port yields. Pause
        -- after a write leaves it unacknowledged; restart truncates to durable offset.
        busy = true
        local wrote = call("write", path, first, r.body)
        local readback = wrote == true and call("read", path, first, count) or nil
        if paused then busy = false; return false, "paused" end
        if wrote ~= true or readback ~= r.body or call("size", path) ~= last + 1 then
            busy = false; return fail("write_readback_failed")
        end
        local next_record = record(last + 1, next_entity)
        local committed = call("checkpoint", copy(next_record))
        busy = false
        if committed ~= true then return fail("checkpoint_failed") end
        durable, self.offset, entity = next_record, last + 1, next_entity
        self.state = paused and "PAUSED" or (self.offset == job.size and "DOWNLOADED" or "DOWNLOADING")
        return true
    end
    function self:verify()
        if busy then return false, "busy" end
        if paused then return false, "paused" end
        if not job or self.offset ~= job.size then return false, "incomplete" end
        if type(port.verify_file) ~= "function" then return fail("verifier_unavailable") end
        busy = true
        local result = call("verify_file", path, copy(job))
        busy = false
        if paused then return false, "paused" end
        if call("size", path) ~= job.size or type(result) ~= "table" or result.size ~= job.size
            or result.md5 ~= job.md5 or result.sha256 ~= job.sha256 or result.signature_valid ~= true then
            return fail("verification_failed")
        end
        self.state, self.error = "VERIFIED", nil
        return true
    end
    return self
end
return M
