box.cfg{
  listen = 3305;
  engine = memtx;
  memtx_memory=2*1024*1024*1024
}

json = require('json')


box.schema.user.create('otuspg', { password = 'learn4otus',if_not_exists = true })
box.schema.user.grant('otuspg', 'read,write,execute,create,drop,alter', 'universe',nil, {if_not_exists = true})

function init_schema()
  box.schema.space.create('dialogs', {if_not_exists = true})
  box.space.dialogs:format({
      {name = 'dialogid', type = 'string'},
      {name = 'sender', type = 'string'},
      {name = 'recepient', type = 'string'},
      {name = 'msgtext', type = 'string'},
      {name = 'msgtime', type = 'double'},
  })
  box.space.dialogs:create_index('primary', {type = 'TREE', parts = {'dialogid','msgtime'}, if_not_exists = true})
  box.space.dialogs:create_index('dialogid', {parts = {'dialogid'}, unique = false, if_not_exists = true})
end

function init_counters()
  box.schema.space.create('counters', {if_not_exists = true})
  box.schema.space.create('counters', {if_not_exists = true})
  box.space.counters:format({
      {name = 'dialogid', type = 'string'},
      {name = 'userid', type = 'string'},
      {name = 'unread', type = 'unsigned'},
    })
  box.space.counters:create_index('primary', {type = 'TREE', parts = {'dialogid','userid'}, if_not_exists = true})
  box.space.counters:create_index('foruser', {type = 'TREE', parts = {'userid'}, unique = false, if_not_exists = true})
end
--dialogs functions
function gen_dialogid(u_send, u_recep)
  local dialogid
  if u_send > u_recep then
    dialogid = u_send .. '-' .. u_recep
  else
    dialogid = u_recep .. '-' .. u_send
  end
  return dialogid
end

function dialogs_add(msg_send,msg_recep,msg_text, msg_time)
  local dialogid = gen_dialogid(msg_send,msg_recep)
  box.space.dialogs:insert({dialogid,msg_send,msg_recep,msg_text,msg_time})
  return dialogid
end

function dialogs_getlist(msg_send, msg_recep, plimit, poffset)
  local dialogid = gen_dialogid(msg_send,msg_recep)
  local results = {}
  local sortind = box.space.dialogs.index.primary:select({dialogid}, {iterator = box.index.REQ, offset=poffset, limit=plimit})
  for _, tpost in pairs(sortind)
    do
      table.insert(results,json.encode({from = tpost['sender'], to = tpost['recepient'], at = tpost['msgtime'], text = tpost['msgtext']}))
    end
  return results
end

--dialogs functions
function create_counter(msg_send, msg_recep)
  local dialogid = gen_dialogid(msg_send,msg_recep)
  local newcounter = box.space.counters:insert{dialogid,msg_recep,0}
  return newcounter
end

function get_counter(msg_send, msg_recep)
  local dialogid = gen_dialogid(msg_send,msg_recep)
  local iscounter = box.space.counters.index.primary:count({dialogid,msg_recep})
  if iscounter == 0 then 
      local actual = create_counter(msg_send, msg_recep) 
      return actual[3]
    end
  if iscounter == 1 then 
      local actual = box.space.counters.index.primary:get({dialogid,msg_recep}) 
      return actual[3]
    end
  if iscounter > 1 then return nil end
end

function counters_increment(msg_send, msg_recep, count)
  local dialogid = gen_dialogid(msg_send,msg_recep)
  local actual = get_counter(msg_send, msg_recep)
  newval = box.space.counters:update({dialogid,msg_recep},{{'+', 3, count}})
  if not newval then
    return nil
  else
    return newval[3] - actual
  end
end
  
function counters_decrement(msg_send, msg_recep, count)
  local dialogid = gen_dialogid(msg_send,msg_recep)
  local actual = get_counter(msg_send, msg_recep)
  if actual > count then
    newval = box.space.counters:update({dialogid,msg_recep},{{'-', 'unread', count}})
  else
    newval = box.space.counters:update({dialogid,msg_recep},{{'=', 'unread', 0}})
  end
  if not newval then
    return nil
  else
    return actual - newval[3]
  end
end

function get_user_counters(msg_send)
  local results = {}
  local usercounters = box.space.counters.index.foruser:select({msg_send})
  for _, tuple in pairs(usercounters)
    do
      table.insert(results,json.encode({dialogid = tuple['dialogid'], unread = tuple['unread']}))
    end
  return results
end

init_schema()
init_counters()