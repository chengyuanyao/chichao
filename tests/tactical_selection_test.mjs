import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createTacticalSelection} from '../public/tactical_selection.js';
const tank={id:'t',kind:'tank',owner:'me',hp:100},dog={id:'d',kind:'dog',owner:'me',hp:50};
const enemy={...tank,id:'enemy',owner:'them'},miner={...dog,id:'m',kind:'harvester'};
let units=[tank,dog,enemy,miner];
const filter=createTacticalSelection();
assert.equal(filter.sync(units,new Set(['t','d','m','enemy']),'me').total,3);
assert.deepEqual(filter.filter('tank'),['t']);
assert.equal(filter.sync(units,new Set(['t']),'me').groups.length,3);
assert.deepEqual(filter.filter('dog'),['d']);
assert.deepEqual(filter.filter(''),['t','d','m']);
filter.sync(units,new Set(['m']),'me');
assert.deepEqual(filter.filter(''),['m'],'new selection resets source');
filter.sync(units,new Set(['t','d']),'me');filter.filter('tank');
dog.hp=0;
assert.equal(filter.sync(units,new Set(['t']),'me').total,1);
assert.deepEqual(filter.filter(''),['t']);
filter.sync(units,new Set(),'me');assert.deepEqual(filter.filter(''),[]);
dog.hp=50;

const source=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
const extract=name=>source.match(new RegExp('  function '+name+'\\([^]*?\\n  \\}'))[0];
const commands=[];
const context={session:{playerId:'me'},roomState:{status:'playing',game:{units}},gameKey:'game1',
  selectedUnits:new Set(['t','d','m','enemy']),tacticalSelection:createTacticalSelection(),
  selectedStructureId:'old',selectedResourceId:'ore',unitRole:k=>k==='harvester'?'harvester':'combat',
  renderSelectionInfo(){},sound(){},toast(){},cancelModes(){},sendAction:(a,p)=>{commands.push(p);return Promise.resolve({});}};
vm.createContext(context);vm.runInContext(extract('filterSelectedKind')+extract('tacticalSelected'),context);
context.filterSelectedKind('tank');assert.deepEqual([...context.selectedUnits],['t']);
assert.equal(commands.length,0,'filter never sends orders');
context.tacticalSelected('hold');await Promise.resolve();assert.equal(commands[0].command,'hold');
assert.deepEqual([...commands[0].unitIds],['t']);
context.selectedUnits=new Set(['t','d','m','enemy']);context.tacticalSelected('scatter');await Promise.resolve();
assert.deepEqual([...commands[1].unitIds],['t','d']);
assert.match(source,/orderedCommands = \[[^\n]*'hold', 'scatter'/);
console.log('Tactical UI passed: mixed filtering/restoration/deaths/ownership, no command side effects, combat-only ordered actions.');
