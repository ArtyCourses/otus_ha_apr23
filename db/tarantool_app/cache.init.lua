box.cfg{
  listen = 3301;
  engine = memtx;
  memtx_memory=1*1024*1024*1024;
  log_level = 6;
}

conf_pg = require('pg')
json = require('json')

pgconn = conf_pg.connect({
  host = 'postgres',
  port = 5432,
  user = 'otuspg',
  password = 'learn4otus',
  db = 'SocialOtus'
})

feedlimit = 1000 


box.schema.user.create('otuspg', { password = 'learn4otus',if_not_exists = true })
box.schema.user.grant('otuspg', 'read,write,execute,create,drop,alter', 'universe',nil, {if_not_exists = true})

function init_schema()
  -- создаем space для кеша постов
  box.schema.space.create('post_cache', {if_not_exists = true})
  box.space.post_cache:format({
      {name = 'post_id', type = 'string'},
      {name = 'created', type = 'unsigned'},
      {name = 'content', type = 'string'},
      {name = 'author_id', type = 'string'},
  })
  box.space.post_cache:create_index('postid', {type = 'TREE', parts = {'post_id'}, if_not_exists = true})
  box.space.post_cache:create_index('created', {parts = {'created'}, unique = false, if_not_exists = true})

  -- создаем space для кеша лент новостей друзей
  box.schema.sequence.create('id_seq',{if_not_exists = true})
  box.schema.space.create('feed_cache', {if_not_exists = true})
  box.space.feed_cache:format({
    {name = 'num_id', type = 'unsigned'},
    {name = 'userid', type = 'string'},
    {name = 'postid', type = 'string'},
    {name = 'created', type = 'unsigned'},
  })

  box.space.feed_cache:create_index('primary',{sequence='id_seq', if_not_exists = true})
  box.space.feed_cache:create_index('userid', {parts = {'userid'}, unique = false, if_not_exists = true})
  box.space.feed_cache:create_index('postid', {parts = {'postid'}, unique = false, if_not_exists = true})
  box.space.feed_cache:create_index('userid_created', {parts = {{'userid'},{'created'}}, unique = false, if_not_exists = true})
  -- подключить триггер инвалидации кеша
  box.space.feed_cache:on_replace(trim_user_feed)
end


function cache_post_frompg(id)
  -- получение поста из БД
  local res, ok = pgconn:execute('select id, author_userid, content, post_date as created from posts where id = uuid($1)', id)
  if not res then error(ok) end
  if #res[1] == 0 then return box.NULL end
  if #res[1] == 1 then return res[1][1] end
  return box.NULL
end


function get_post(id)
  -- прочитать пост id
  local post = box.space.post_cache.index.postid:get(id)
  if not post then
    local dbpost = cache_post_frompg(id)
    if dbpost ~= box.NULL then
      post = box.space.post_cache:insert({dbpost.id, dbpost.created, dbpost.content, dbpost.author_userid})
    end
  end
  return post
  end


function update_cachepost(id)
  -- обновить пост из БД (когда изменился текст поста)
  local res, ok = pgconn:execute('select content from posts where id =uuid($1)', id)
  if not res then error(ok) end
  if #res[1] == 0 then return nil end
  if #res[1] == 1 then
    box.space.post_cache:update(id,{{'=','content',res[1][1]['content']}})
    end
  return get_post(id)
  end

function trim_user_feed(old_tuple, new_tuple, tek_space, tek_op)
-- триггер, по событию вставки поста в ленту проверяется новую длину ленты пользователя которому добавился пост в ленту, если она больше разрешенного - то удаляет самые старые посты пока длина не станет разрешенной
if tek_op == 'INSERT' then
  local userid = new_tuple['userid']
  local post_count = box.space.feed_cache.index.userid:count(userid)
  if post_count > feedlimit then
    while post_count > feedlimit do
      local old_posts = box.space.feed_cache.index.userid_created:min(userid)
      local del_id = old_posts['postid']
      box.space.feed_cache:delete(old_posts[1])
      local post_in_feeds = box.space.post_cache.index.postid:select({ del_id })
      if #post_in_feeds ~= 0 then
        box.space.post_cache.index.postid:delete(del_id)
        end
      post_count = post_count - 1
      end
    end
  end
end

function add_postfeed(feed_owner, postid)
-- добавить пост в ленту пользователю 
  local tpost = get_post(postid)
  box.space.feed_cache:insert({box.Null,feed_owner, postid, tpost['created']})
end

function get_feed(userid,plimit,poffset)
-- получить ленту постов пользователя
  local results = {}
  local sortind = box.space.feed_cache.index.userid_created:select({userid}, {iterator = box.index.REQ, offset=poffset, limit=plimit})
  for _, tuple in pairs(sortind)
    do
      local tpost = box.space.post_cache.index.postid:get(tuple['postid'])
      table.insert(results,json.encode({id = tpost['post_id'], text = tpost['content'],author_user_id = tpost['author_id'], created = tpost['created']}))
    end
  return results
end

function rebuildcache()
-- ребилд кеша из БД: очистить рабочие space и загрузить данный из БД. Заполняем кеш только постами авторов, которые добавлены в друзья.
  if box.space.post_cache:count() > 0 then box.space.post_cache:truncate() end
  if box.space.feed_cache:count() > 0 then 
      box.space.feed_cache:truncate()
      box.sequence.id_seq:reset()
    end  
  local synccnt = feedlimit*feedlimit
  local authlst, ok = pgconn:execute('select distinct id as postid, author_userid as authorid, post_date as created from posts p join friendships fs on p.author_userid = fs.friendid order by p.post_date DESC limit $1;',synccnt)
  if not authlst then error(ok) end
  if #authlst[1] == 0 then return nil end
  for _, tekauth in pairs(authlst[1]) do
    local folowlst, flok = pgconn:execute('select userid from friendships where friendid = uuid($1);',tekauth['authorid'])
    if not folowlst[1] then error(flok) end
    if #folowlst[1] == 0 then return nil end
    for _, tekfolow in pairs(folowlst[1]) do
      add_postfeed(tekfolow['userid'],tekauth['postid'])
    end
  end
  return true
end

-- вызовем создание схемы (если отсутвует) и ребилд кеша при старте пода с тарантулом
init_schema()
rebuildcache()