'use strict'

const fs = require('node:fs')
const path = require('node:path')
const readline = require('node:readline')
const { configValid, observe, heardSound, validateCommand, distance, motorProximity } = require('./senses')
const mineflayer = require('mineflayer')
const { ACTIONS, validateHands, executeHands, snapshot } = require('./hands')
const survival = require('./survival-body')
const { CHANNELS, validateMuscle, activateMuscle, proprioception } = require('./muscle-body')
let actionEpoch = 0
const config = configValid(JSON.parse(fs.readFileSync(process.argv[2] || path.join(__dirname, 'config.json'), 'utf8')))
const send = (kind, content) => process.stdout.write(JSON.stringify({ protocol: 1, kind, content }) + '\n')
let bot
let ready = false
let sequence = 0
let lastHeartbeat = Date.now()
let moveTimer = null
let moveResolve = null
let closing = false
let busy = false
let autonomousMove = null
let seen = new Set()
let lastSense = ''
const { chooseView } = require('./observer-view')
const cameraFile = path.join(__dirname, '../work/camera-view.json')
const cameraSettings = path.join(__dirname, '../work/camera-settings.json')
let previousCamera = {}
const cameraTimer = setInterval(() => {
  if (!ready || !bot.entity) return
  try {
    const settings = JSON.parse(fs.readFileSync(cameraSettings,'utf8'))
    if (!settings.enabled) return
    const views = {}
    for (const [player, options] of Object.entries(settings.players || {})) {
      if (options.mode === 'first') continue
      const view = chooseView(bot, Math.max(4,Math.min(20,Number(options.distance)||8)), previousCamera[player], options.mode)
      if (view.clear) previousCamera[player]=view.position
      views[player]=view
    }
    fs.writeFileSync(cameraFile+'.tmp',JSON.stringify({players:views}))
    fs.renameSync(cameraFile+'.tmp',cameraFile)
  } catch (_) {} // Operator telemetry must never stop cognition.
},50)


function stop () {
  actionEpoch++
  if (bot) {
    if (bot.pathfinder) bot.pathfinder.setGoal(null)
    if (bot.targetDigBlock) bot.stopDigging()
    bot.deactivateItem()
    if (bot.currentWindow) bot.closeWindow(bot.currentWindow)
  }
  autonomousMove = null
  clearTimeout(moveTimer)
  moveTimer = null
  if (moveResolve) { const resolve = moveResolve; moveResolve = null; resolve() }
  if (bot) bot.clearControlStates()
}
function shutdown () {
  if (closing) return
  closing = true
  stop()
  clearInterval(cameraTimer)
  clearInterval(senses)
  clearInterval(watchdog)
  if (bot) bot.quit('Synthetic Mind stopped')
  setTimeout(() => process.exit(0), 250).unref()
}

// Mineflayer warnings belong on stderr; stdout is an NDJSON protocol channel.
console.log = (...args) => console.error(...args)
bot = mineflayer.createBot({ host: config.host, port: config.port, version: config.version,
  username: config.username, auth: 'offline', viewDistance: 'tiny', hideErrors: true, respawn: false })
if (config.survival) survival.install(bot)
let lives = 0
bot.on('spawn', () => {
  lives++; busy=false; lastSense='';
  if(lives>1)send('minecraft.respawned',{life:lives})
  ready = true
  lastHeartbeat = Date.now()
  send('minecraft.connected', { username: bot.username, version: bot.version, host: config.host, port: config.port, muscle_channels: CHANNELS, body_revision: 'muscle-body-v2' })
})
bot.on('error', error => send('minecraft.error', { message: error.message }))
bot.on('kicked', reason => { stop(); send('minecraft.kicked', { reason: typeof reason === 'string' ? reason : JSON.stringify(reason) }) })
bot.on('end', reason => { ready = false; stop(); send('minecraft.disconnected', { reason: String(reason || 'connection ended') }); shutdown() })
bot.on('death', () => { stop(); send('minecraft.death', {position:bot.entity?.position}); ready = false
 if(config.survival)setTimeout(()=>{if(!closing)bot.respawn()},2000)
})
bot.on('entityHurt',(entity,source)=>{if(entity?.id===bot.entity?.id)send('minecraft.damage',{source_type:source?.name||null,source_id:source?.id??null,attribution:source?'server':'unknown',health:bot.health,position:bot.entity.position})})
bot.on('sleep',()=>send('minecraft.sleep',{sleeping:true,timeOfDay:bot.time?.timeOfDay}))
bot.on('wake',()=>send('minecraft.sleep',{sleeping:false,timeOfDay:bot.time?.timeOfDay}))
bot.on('physicsTick', () => {
  if (!autonomousMove || autonomousMove.skill === 'embodied' || !bot.entity || !bot.entity.onGround) return
  const proximity = motorProximity(bot, 0.65)
  if (proximity.hazardAhead || ((!proximity.supportedAhead || proximity.obstructedAhead) && !(autonomousMove.jump && proximity.canStepUp))) {
    const commandId = autonomousMove.id
    stop()
    send('minecraft.reflex', { command_id: commandId, reason: 'Fresh local proximity interrupted motor pulse', proximity })
  }
})
bot.on('chat', (username, text) => {
  if (username === bot.username || /^!camera(?: |$)/i.test(text)) return
  if (username.toLowerCase() === 'firmlygrasp1t' && /^!(start|stop|shutdown|camera)(?: |$)/i.test(text)) {
    send('minecraft.chat', { username, text: text.slice(0, 1000), sensoryModel: 'operator-control' })
    return
  }
  const player = bot.players[username]
  if (!player || !player.entity || !bot.entity || distance(player.entity.position, bot.entity.position) > config.hearingRange) return
  send('minecraft.chat', { username, text: text.slice(0, 1000), sensoryModel: 'nearby-game-chat-v1' })
})
bot.worldTickRate = 20
bot._client.on('set_ticking_state', packet => {
  if (Number.isFinite(packet.tick_rate) && packet.tick_rate > 0) bot.worldTickRate = packet.tick_rate
  send('minecraft.clock', { worldTickRate: bot.worldTickRate, frozen: Boolean(packet.is_frozen) })
})
bot._client.on('sound_effect', packet => { const sound = heardSound(bot, config, packet); if (sound) send('minecraft.sound', sound) })
bot._client.on('named_sound_effect', packet => { const sound = heardSound(bot, config, packet); if (sound) send('minecraft.sound', sound) })

const senses = setInterval(() => {
  if (!ready || closing || !bot.entity || !Number.isFinite(bot.health) || !Number.isFinite(bot.food)) return
  try {
    const snapshot = observe(bot, config, ++sequence)
    const signature = JSON.stringify({ ...snapshot, sequence: 0 })
    if (signature === lastSense) return
    lastSense = signature
    send('minecraft.senses', snapshot)
  } catch (error) { send('minecraft.error', { message: `Sensing: ${error.message}` }) }
}, config.senseIntervalMs)
const watchdog = setInterval(() => { if (Date.now() - lastHeartbeat > config.leaseMs) stop() }, 250)

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity })
input.on('line', async line => {
  let command
  let ownsMotor = false
  try {
    if (line.length > 8192) throw new Error('Command exceeds protocol limit')
    command = validateCommand(JSON.parse(line))
    if (ACTIONS.includes(command.action)) validateHands(command)
    if (command.action === 'heartbeat') { lastHeartbeat = Date.now(); return }
    if (command.action === 'disconnect') { shutdown(); return }
    if (Date.now() - lastHeartbeat > config.leaseMs && command.action !== 'stop') throw new Error('Control lease expired; waiting for parent heartbeat')
    if (!ready) throw new Error('Bot is not ready (not spawned, disconnected, or dead)')
    if (seen.has(command.id)) return
    if (busy && !['stop', 'say'].includes(command.action)) throw new Error('Motor command already running')
    seen.add(command.id)
    if (seen.size > 4096) seen = new Set([...seen].slice(-2048))
    ownsMotor = !['stop', 'say'].includes(command.action)
    if (command.action === 'stop') stop()
    else if (command.action === 'move') {
      stop()
      const before = { x: bot.entity.position.x, y: bot.entity.position.y, z: bot.entity.position.z }
      busy = true
      const stepEpoch = actionEpoch
      if (command.target) await require('./directed-step').orient(bot, command)
      if (closing || !ready || actionEpoch !== stepEpoch || Date.now()-lastHeartbeat>config.leaseMs) throw Error('Directed step cancelled')
      if (command.skill && command.control === 'forward') autonomousMove = command
      bot.setControlState(command.control, true)
      if (command.jump) bot.setControlState('jump', true)
      await new Promise(resolve => { moveResolve = resolve; moveTimer = setTimeout(resolve, config.movementDurationMs) })
      stop()
      busy = false
      send('minecraft.action_result', { command_id: command.id, action: command.action, control: command.control, before,
        position: { x: bot.entity.position.x, y: bot.entity.position.y, z: bot.entity.position.z }, after: proprioception(bot),
        contact: Boolean(bot.entity.isCollidedHorizontally) })
      return
    } else if (command.action === 'look') {
      busy = true
      const before = proprioception(bot)
      await bot.look(command.yaw, command.pitch, false)
      busy = false
      send('minecraft.action_result', {command_id:command.id,action:'look',before,after:proprioception(bot),verified:true})
      return
    }
    else if (command.action === 'say') bot.chat(command.text)
    else if (command.action === 'muscle') {
      validateMuscle(command)
      busy = true
      const epoch = actionEpoch
      let timer
      try {
        const result = await Promise.race([activateMuscle(bot, command, { check: () => { if (actionEpoch !== epoch || !ready) throw new Error('Activation cancelled') } }),
          new Promise((resolve, reject) => { timer = setTimeout(() => { stop(); ready = false; reject(new Error('Activation timed out; reconnect required')); shutdown() }, 6000) })])
        send('minecraft.action_result', { command_id: command.id, action: 'muscle', channel: command.channel, ...result })
      } finally { clearTimeout(timer); busy = false }
      return
    }
    else if (survival.ROUTINES.includes(command.action)) {
      if(!config.survival)throw Error('Survival routines are disabled')
      busy=true; const epoch=actionEpoch; let timer
      try {
        const result=await Promise.race([survival.execute(bot,command,()=>{if(epoch!==actionEpoch||!ready)throw Error('Routine cancelled')}),new Promise((resolve,reject)=>{timer=setTimeout(()=>{stop();reject(Error('Bounded routine timed out'))},20000)})])
        send('minecraft.action_result',{command_id:command.id,action:command.action,target:command.target,item:command.item,...result})
      }finally{clearTimeout(timer);busy=false;bot.pathfinder.setGoal(null);bot.clearControlStates()}
      return
    }
    else if (ACTIONS.includes(command.action)) {
      busy = true
      const epoch = actionEpoch
      let timer
      try {
        const result = await Promise.race([executeHands(bot, command, () => { if (actionEpoch !== epoch) throw new Error('Action cancelled') }),
          new Promise((resolve, reject) => { timer = setTimeout(() => { stop(); ready = false; reject(new Error('Hand action timed out; reconnect required')); shutdown() }, 10000) })])
        send('minecraft.action_result', { command_id: command.id, action: command.action, item: command.item, target: command.target, ...result })
      } finally { clearTimeout(timer); busy = false }
      return
    }
    else if (command.action === 'eat') {
      const edible = bot.inventory.items().find(item => bot.registry.foodsByName && bot.registry.foodsByName[item.name])
      if (!edible) throw new Error('No edible item in inventory')
      const before = snapshot(bot)
      const epoch = actionEpoch
      busy = true
      await bot.equip(edible, 'hand')
      if (epoch !== actionEpoch) throw new Error('Eating cancelled')
      await bot.consume()
      busy = false
      send('minecraft.action_result', { command_id: command.id, action: 'eat', before, after: snapshot(bot), verified: bot.food > before.food })
      return
    }
    send('minecraft.action_result', { command_id: command.id, action: command.action, ok: true, motor_busy: busy })
  } catch (error) {
    if (ownsMotor) {
      busy = false
      stop()
    }
    send('minecraft.command_error', { command_id: command ? command.id : null, action: command?.action, message: error.message })
  }
})
input.on('close', shutdown)
process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
