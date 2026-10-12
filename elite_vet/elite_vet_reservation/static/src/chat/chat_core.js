/* Shared booking state: same API and validation as the website form. */
(function (root) {
    'use strict';
    class Booking {
        constructor(rpc) { this.rpc=rpc; this.details={}; this.status='editing'; }
        async load() { this.options=await this.rpc('/rezervace/api/options',{}); return this.options; }
        filters() { return {procedure_id:this.procedure.id, doctor_id:this.doctor ? this.doctor.id : false}; }
        async days(year,month) { return this.rpc('/rezervace/api/days',Object.assign(this.filters(),{year,month})); }
        async slots() { return this.rpc('/rezervace/api/slots',Object.assign(this.filters(),{date:this.date})); }
        async submit(consent) {
            if(this.status!=='editing') throw Error(this.status);
            if(consent!==true) throw Error('consent');
            if(!this.procedure || !this.date || !this.time) throw Error('selection');
            const required=['contact_name','contact_email','contact_phone','pet_name','pet_species','problem'];
            if(required.some(k=>!String(this.details[k]||'').trim())) throw Error('details');
            this.status='busy';
            let slots;
            try { slots=await this.slots(); } catch(e) { this.status='editing'; throw e; }
            if(!slots.some(s=>s.time===this.time)) { this.status='editing'; throw Error('slot_taken'); }
            const payload=Object.assign({},this.details,this.filters(),{date:this.date,time:this.time,consent:true,hp:''});
            let result;
            try { result=await this.rpc('/rezervace/api/submit',payload); }
            catch(e) { this.status='uncertain'; throw Error('uncertain'); }
            if(!result || typeof result.ok!=='boolean') { this.status='uncertain'; throw Error('uncertain'); }
            this.status=result.ok ? 'done' : 'editing';
            return result;
        }
    }
    if(typeof module==='object' && module.exports) module.exports=Booking;
    else root.EliteVetChatBooking=Booking;
})(typeof window==='object' ? window : this);
