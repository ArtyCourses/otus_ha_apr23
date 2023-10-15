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

function dialogs_getlist(msg_send, msg_recep, plimit)
  local dialogid = gen_dialogid(msg_send,msg_recep)
  local results = {}
  local sortind = box.space.dialogs.index.primary:select({dialogid}, {iterator = box.index.REQ, limit=plimit})
  for _, tpost in pairs(sortind)
    do
      table.insert(results,json.encode({from = tpost['sender'], to = tpost['recepient'], at = tpost['msgtime'], text = tpost['msgtext']}))
    end
  return results
end

init_schema()
