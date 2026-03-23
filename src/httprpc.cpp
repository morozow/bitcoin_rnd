// Copyright (c) 2015-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <httprpc.h>

#include <common/args.h>
#include <crypto/hmac_sha256.h>
#include <httpserver.h>
#include <logging.h>
#include <netaddress.h>
#include <node/stdio_bus_hooks.h>
#include <rpc/protocol.h>
#include <rpc/server.h>
#include <util/fs.h>
#include <util/fs_helpers.h>
#include <util/strencodings.h>
#include <util/string.h>
#include <walletinitinterface.h>

#include <algorithm>
#include <iterator>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

using util::SplitString;
using util::TrimStringView;

/** WWW-Authenticate to present with 401 Unauthorized response */
static const char* WWW_AUTH_HEADER_DATA = "Basic realm=\"jsonrpc\"";

/* List of -rpcauth values */
static std::vector<std::vector<std::string>> g_rpcauth;
/* RPC Auth Whitelist */
static std::map<std::string, std::set<std::string>> g_rpc_whitelist;
static bool g_rpc_whitelist_default = false;

//! stdio_bus hooks for RPC monitoring (Phase 5)
static std::shared_ptr<node::StdioBusHooks> g_httprpc_stdio_bus_hooks;

/**
 * @brief Set stdio_bus hooks for HTTP RPC
 * Called from init.cpp when stdio_bus is enabled.
 */
void SetHttpRpcStdioBusHooks(std::shared_ptr<node::StdioBusHooks> hooks)
{
    g_httprpc_stdio_bus_hooks = std::move(hooks);
}

static void JSONErrorReply(HTTPRequest* req, UniValue objError, const JSONRPCRequest& jreq)
{
    // Sending HTTP errors is a legacy JSON-RPC behavior.
    Assume(jreq.m_json_version != JSONRPCVersion::V2);

    // Send error reply from json-rpc error object
    int nStatus = HTTP_INTERNAL_SERVER_ERROR;
    int code = objError.find_value("code").getInt<int>();

    if (code == RPC_INVALID_REQUEST)
        nStatus = HTTP_BAD_REQUEST;
    else if (code == RPC_METHOD_NOT_FOUND)
        nStatus = HTTP_NOT_FOUND;

    std::string strReply = JSONRPCReplyObj(NullUniValue, std::move(objError), jreq.id, jreq.m_json_version).write() + "\n";

    req->WriteHeader("Content-Type", "application/json");
    req->WriteReply(nStatus, strReply);
}

//This function checks username and password against -rpcauth
//entries from config file.
static bool CheckUserAuthorized(std::string_view user, std::string_view pass)
{
    for (const auto& fields : g_rpcauth) {
        if (!TimingResistantEqual(std::string_view(fields[0]), user)) {
            continue;
        }

        const std::string& salt = fields[1];
        const std::string& hash = fields[2];

        std::array<unsigned char, CHMAC_SHA256::OUTPUT_SIZE> out;
        CHMAC_SHA256(UCharCast(salt.data()), salt.size()).Write(UCharCast(pass.data()), pass.size()).Finalize(out.data());
        std::string hash_from_pass = HexStr(out);

        if (TimingResistantEqual(hash_from_pass, hash)) {
            return true;
        }
    }
    return false;
}

static bool RPCAuthorized(const std::string& strAuth, std::string& strAuthUsernameOut)
{
    if (!strAuth.starts_with("Basic "))
        return false;
    std::string_view strUserPass64 = TrimStringView(std::string_view{strAuth}.substr(6));
    auto userpass_data = DecodeBase64(strUserPass64);
    std::string strUserPass;
    if (!userpass_data) return false;
    strUserPass.assign(userpass_data->begin(), userpass_data->end());

    size_t colon_pos = strUserPass.find(':');
    if (colon_pos == std::string::npos) {
        return false; // Invalid basic auth.
    }
    std::string user = strUserPass.substr(0, colon_pos);
    std::string pass = strUserPass.substr(colon_pos + 1);
    strAuthUsernameOut = user;
    return CheckUserAuthorized(user, pass);
}

static bool HTTPReq_JSONRPC(const std::any& context, HTTPRequest* req)
{
    // Phase 5: Get request_id from HTTP layer for event correlation
    int64_t request_id = req->GetStdioBusRequestId();
    std::string peer_addr = req->GetPeer().ToStringAddrPort();
    std::string rpc_method;
    
    // JSONRPC handles only POST
    if (req->GetRequestMethod() != HTTPRequest::POST) {
        req->WriteReply(HTTP_BAD_METHOD, "JSONRPC server handles only POST requests");
        return false;
    }
    // Check authorization
    std::pair<bool, std::string> authHeader = req->GetHeader("authorization");
    if (!authHeader.first) {
        req->WriteHeader("WWW-Authenticate", WWW_AUTH_HEADER_DATA);
        req->WriteReply(HTTP_UNAUTHORIZED);
        return false;
    }

    JSONRPCRequest jreq;
    jreq.context = context;
    jreq.peerAddr = peer_addr;
    if (!RPCAuthorized(authHeader.second, jreq.authUser)) {
        LogWarning("ThreadRPCServer incorrect password attempt from %s", jreq.peerAddr);

        /* Deter brute-forcing
           If this results in a DoS the user really
           shouldn't have their RPC port exposed. */
        UninterruptibleSleep(std::chrono::milliseconds{250});

        req->WriteHeader("WWW-Authenticate", WWW_AUTH_HEADER_DATA);
        req->WriteReply(HTTP_UNAUTHORIZED);
        return false;
    }

    try {
        // Parse request
        UniValue valRequest;
        if (!valRequest.read(req->ReadBody()))
            throw JSONRPCError(RPC_PARSE_ERROR, "Parse error");

        // Set the URI
        jreq.URI = req->GetURI();

        UniValue reply;
        bool user_has_whitelist = g_rpc_whitelist.contains(jreq.authUser);
        if (!user_has_whitelist && g_rpc_whitelist_default) {
            LogWarning("RPC User %s not allowed to call any methods", jreq.authUser);
            req->WriteReply(HTTP_FORBIDDEN);
            return false;

        // singleton request
        } else if (valRequest.isObject()) {
            jreq.parse(valRequest);
            rpc_method = jreq.strMethod;
            
            if (user_has_whitelist && !g_rpc_whitelist[jreq.authUser].contains(jreq.strMethod)) {
                LogWarning("RPC User %s not allowed to call method %s", jreq.authUser, jreq.strMethod);
                req->WriteReply(HTTP_FORBIDDEN);
                return false;
            }

            int64_t exec_start_us = node::GetMonotonicTimeUs();
            
            const bool catch_errors{jreq.m_json_version == JSONRPCVersion::V2};
            reply = JSONRPCExec(jreq, catch_errors);
            
            int64_t exec_end_us = node::GetMonotonicTimeUs();

            if (jreq.IsNotification()) {
                req->WriteReply(HTTP_NO_CONTENT);
                
                // Phase 5: Fire lifecycle event
                if (g_httprpc_stdio_bus_hooks && g_httprpc_stdio_bus_hooks->Enabled() && request_id >= 0) {
                    node::RpcCallLifecycleEvent ev;
                    ev.request_id = request_id;
                    ev.method = rpc_method;
                    ev.peer_addr = peer_addr;
                    ev.exec_start_us = exec_start_us;
                    ev.exec_end_us = exec_end_us;
                    ev.success = true;
                    ev.http_status = HTTP_NO_CONTENT;
                    ev.response_size = 0;
                    g_httprpc_stdio_bus_hooks->OnRpcCallLifecycle(ev);
                }
                return true;
            }

        // array of requests
        } else if (valRequest.isArray()) {
            if (user_has_whitelist) {
                for (unsigned int reqIdx = 0; reqIdx < valRequest.size(); reqIdx++) {
                    if (!valRequest[reqIdx].isObject()) {
                        throw JSONRPCError(RPC_INVALID_REQUEST, "Invalid Request object");
                    } else {
                        const UniValue& request = valRequest[reqIdx].get_obj();
                        std::string strMethod = request.find_value("method").get_str();
                        if (!g_rpc_whitelist[jreq.authUser].contains(strMethod)) {
                            LogWarning("RPC User %s not allowed to call method %s", jreq.authUser, strMethod);
                            req->WriteReply(HTTP_FORBIDDEN);
                            return false;
                        }
                    }
                }
            }

            rpc_method = "[batch]";
            
            reply = UniValue::VARR;
            for (size_t i{0}; i < valRequest.size(); ++i) {
                UniValue response;
                try {
                    jreq.parse(valRequest[i]);
                    response = JSONRPCExec(jreq, /*catch_errors=*/true);
                } catch (UniValue& e) {
                    response = JSONRPCReplyObj(NullUniValue, std::move(e), jreq.id, jreq.m_json_version);
                } catch (const std::exception& e) {
                    response = JSONRPCReplyObj(NullUniValue, JSONRPCError(RPC_PARSE_ERROR, e.what()), jreq.id, jreq.m_json_version);
                }
                if (!jreq.IsNotification()) {
                    reply.push_back(std::move(response));
                }
            }
            
            if (reply.size() == 0 && valRequest.size() > 0) {
                req->WriteReply(HTTP_NO_CONTENT);
                return true;
            }
        }
        else
            throw JSONRPCError(RPC_PARSE_ERROR, "Top-level object parse error");

        std::string reply_str = reply.write() + "\n";
        req->WriteHeader("Content-Type", "application/json");
        req->WriteReply(HTTP_OK, reply_str);
        
        // Phase 5: Fire lifecycle event for successful request
        if (g_httprpc_stdio_bus_hooks && g_httprpc_stdio_bus_hooks->Enabled() && request_id >= 0) {
            node::RpcCallLifecycleEvent ev;
            ev.request_id = request_id;
            ev.method = rpc_method;
            ev.peer_addr = peer_addr;
            ev.exec_start_us = node::GetMonotonicTimeUs(); // Approximation
            ev.exec_end_us = ev.exec_start_us;
            ev.success = true;
            ev.http_status = HTTP_OK;
            ev.response_size = reply_str.size();
            g_httprpc_stdio_bus_hooks->OnRpcCallLifecycle(ev);
        }
        
    } catch (UniValue& e) {
        JSONErrorReply(req, std::move(e), jreq);
        
        // Phase 5: Fire lifecycle event for failed request
        if (g_httprpc_stdio_bus_hooks && g_httprpc_stdio_bus_hooks->Enabled() && request_id >= 0) {
            node::RpcCallLifecycleEvent ev;
            ev.request_id = request_id;
            ev.method = rpc_method;
            ev.peer_addr = peer_addr;
            ev.exec_start_us = node::GetMonotonicTimeUs();
            ev.exec_end_us = ev.exec_start_us;
            ev.success = false;
            ev.http_status = HTTP_INTERNAL_SERVER_ERROR;
            ev.response_size = 0;
            g_httprpc_stdio_bus_hooks->OnRpcCallLifecycle(ev);
        }
        return false;
    } catch (const std::exception& e) {
        JSONErrorReply(req, JSONRPCError(RPC_PARSE_ERROR, e.what()), jreq);
        
        // Phase 5: Fire lifecycle event for exception
        if (g_httprpc_stdio_bus_hooks && g_httprpc_stdio_bus_hooks->Enabled() && request_id >= 0) {
            node::RpcCallLifecycleEvent ev;
            ev.request_id = request_id;
            ev.method = rpc_method;
            ev.peer_addr = peer_addr;
            ev.exec_start_us = node::GetMonotonicTimeUs();
            ev.exec_end_us = ev.exec_start_us;
            ev.success = false;
            ev.http_status = HTTP_INTERNAL_SERVER_ERROR;
            ev.response_size = 0;
            g_httprpc_stdio_bus_hooks->OnRpcCallLifecycle(ev);
        }
        return false;
    }
    return true;
}

static bool InitRPCAuthentication()
{
    std::string user;
    std::string pass;

    if (gArgs.GetArg("-rpcpassword", "") == "")
    {
        std::optional<fs::perms> cookie_perms{std::nullopt};
        auto cookie_perms_arg{gArgs.GetArg("-rpccookieperms")};
        if (cookie_perms_arg) {
            auto perm_opt = InterpretPermString(*cookie_perms_arg);
            if (!perm_opt) {
                LogError("Invalid -rpccookieperms=%s; must be one of 'owner', 'group', or 'all'.", *cookie_perms_arg);
                return false;
            }
            cookie_perms = *perm_opt;
        }

        switch (GenerateAuthCookie(cookie_perms, user, pass)) {
        case GenerateAuthCookieResult::ERR:
            return false;
        case GenerateAuthCookieResult::DISABLED:
            LogInfo("RPC authentication cookie file generation is disabled.");
            break;
        case GenerateAuthCookieResult::OK:
            LogInfo("Using random cookie authentication.");
            break;
        }
    } else {
        LogInfo("Using rpcuser/rpcpassword authentication.");
        LogWarning("The use of rpcuser/rpcpassword is less secure, because credentials are configured in plain text. It is recommended that locally-run instances switch to cookie-based auth, or otherwise to use hashed rpcauth credentials. See share/rpcauth in the source directory for more information.");
        user = gArgs.GetArg("-rpcuser", "");
        pass = gArgs.GetArg("-rpcpassword", "");
    }

    // If there is a plaintext credential, hash it with a random salt before storage.
    if (!user.empty() || !pass.empty()) {
        // Generate a random 16 byte hex salt.
        std::array<unsigned char, 16> raw_salt;
        GetStrongRandBytes(raw_salt);
        std::string salt = HexStr(raw_salt);

        // Compute HMAC.
        std::array<unsigned char, CHMAC_SHA256::OUTPUT_SIZE> out;
        CHMAC_SHA256(UCharCast(salt.data()), salt.size()).Write(UCharCast(pass.data()), pass.size()).Finalize(out.data());
        std::string hash = HexStr(out);

        g_rpcauth.push_back({user, salt, hash});
    }

    if (!gArgs.GetArgs("-rpcauth").empty()) {
        LogInfo("Using rpcauth authentication.\n");
        for (const std::string& rpcauth : gArgs.GetArgs("-rpcauth")) {
            std::vector<std::string> fields{SplitString(rpcauth, ':')};
            const std::vector<std::string> salt_hmac{SplitString(fields.back(), '$')};
            if (fields.size() == 2 && salt_hmac.size() == 2) {
                fields.pop_back();
                fields.insert(fields.end(), salt_hmac.begin(), salt_hmac.end());
                g_rpcauth.push_back(fields);
            } else {
                LogWarning("Invalid -rpcauth argument.");
                return false;
            }
        }
    }

    g_rpc_whitelist_default = gArgs.GetBoolArg("-rpcwhitelistdefault", !gArgs.GetArgs("-rpcwhitelist").empty());
    for (const std::string& strRPCWhitelist : gArgs.GetArgs("-rpcwhitelist")) {
        auto pos = strRPCWhitelist.find(':');
        std::string strUser = strRPCWhitelist.substr(0, pos);
        bool intersect = g_rpc_whitelist.contains(strUser);
        std::set<std::string>& whitelist = g_rpc_whitelist[strUser];
        if (pos != std::string::npos) {
            std::string strWhitelist = strRPCWhitelist.substr(pos + 1);
            std::vector<std::string> whitelist_split = SplitString(strWhitelist, ", ");
            std::set<std::string> new_whitelist{
                std::make_move_iterator(whitelist_split.begin()),
                std::make_move_iterator(whitelist_split.end())};
            if (intersect) {
                std::set<std::string> tmp_whitelist;
                std::set_intersection(new_whitelist.begin(), new_whitelist.end(),
                       whitelist.begin(), whitelist.end(), std::inserter(tmp_whitelist, tmp_whitelist.end()));
                new_whitelist = std::move(tmp_whitelist);
            }
            whitelist = std::move(new_whitelist);
        }
    }

    return true;
}

bool StartHTTPRPC(const std::any& context)
{
    LogDebug(BCLog::RPC, "Starting HTTP RPC server\n");
    if (!InitRPCAuthentication())
        return false;

    auto handle_rpc = [context](HTTPRequest* req, const std::string&) { return HTTPReq_JSONRPC(context, req); };
    RegisterHTTPHandler("/", true, handle_rpc);
    if (g_wallet_init_interface.HasWalletSupport()) {
        RegisterHTTPHandler("/wallet/", false, handle_rpc);
    }
    struct event_base* eventBase = EventBase();
    assert(eventBase);
    return true;
}

void InterruptHTTPRPC()
{
    LogDebug(BCLog::RPC, "Interrupting HTTP RPC server\n");
}

void StopHTTPRPC()
{
    LogDebug(BCLog::RPC, "Stopping HTTP RPC server\n");
    UnregisterHTTPHandler("/", true);
    if (g_wallet_init_interface.HasWalletSupport()) {
        UnregisterHTTPHandler("/wallet/", false);
    }
}
