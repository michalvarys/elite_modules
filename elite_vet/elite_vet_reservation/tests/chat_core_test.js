const assert = require('assert');
const Booking = require('../static/src/chat/chat_core.js');
(async function () {
 let writes=0, slots=[{time:'10:00'}], resolveWrite;
 const rpc=async (path,p) => {
  if(path.endsWith('options')) return {procedures:[{id:1,name:'Vaccination'}],doctors:[],settings:{}};
  if(path.endsWith('slots')) return slots;
  if(path.endsWith('submit')) {writes++; return new Promise(r=>{resolveWrite=r;});}
 };
 const b=new Booking(rpc); await b.load(); b.procedure=b.options.procedures[0]; b.date='2026-10-13'; b.time='10:00';
 b.details={contact_name:'Test User',pet_name:'Rex',pet_species:'dog',contact_email:'test@example.com',contact_phone:'+420777111222',problem:'Vaccination'};
 await assert.rejects(()=>b.submit(false), /consent/); assert.equal(writes,0);
 slots=[]; await assert.rejects(()=>b.submit(true), /slot_taken/); assert.equal(writes,0);
 slots=[{time:'10:00'}]; const first=b.submit(true); await Promise.resolve(); await Promise.resolve();
 await assert.rejects(()=>b.submit(true), /busy/); assert.equal(writes,1);
 resolveWrite({ok:true}); await first; await assert.rejects(()=>b.submit(true), /done/); assert.equal(writes,1);
 const uncertain=new Booking(async(path)=>{if(path.endsWith('slots'))return slots; throw Error('network');});
 Object.assign(uncertain,{procedure:b.procedure,date:b.date,time:b.time,details:b.details});
 await assert.rejects(()=>uncertain.submit(true), /uncertain/);
 await assert.rejects(()=>uncertain.submit(true), /uncertain/);
 console.log('PASS: consent, slot recheck, concurrent submit, completed and uncertain retry guards');
})().catch(e=>{console.error(e);process.exit(1);});
