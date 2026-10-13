import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const html = readFileSync(new URL('../app/index.html', import.meta.url), 'utf8');
const start = html.indexOf('document.getElementById("gform").addEventListener("change"');
const end = html.indexOf('document.getElementById("run").onclick', start);
let handler;
const state = vm.createContext({
  guidedItems: [{domain:'d_financing_contracts',terms:[],fields:{amount:'100'}}],
  renderCount:0,
  renderGuidedForm() { state.renderCount++; },
  document: { getElementById: () => ({ addEventListener: (_, fn) => { handler=fn; } }) }
});
vm.runInContext(html.slice(start,end),state);
handler({target:{tagName:'SELECT',dataset:{gd:'0'},value:'d_leasing'}});
assert.equal(state.guidedItems[0].domain, 'd_leasing', 'domain selection must survive a form rerender');
assert.equal(state.renderCount, 1, 'required-field badges update when domain changes');
assert.equal(state.guidedItems[0].fields.amount, '100');
handler({target:{tagName:'INPUT',dataset:{g:'0',t:'term-ijara'},checked:true}});
assert.equal(state.guidedItems[0].terms[0],'term-ijara');
handler({target:{tagName:'INPUT',dataset:{g:'0',f:'asset_owner'},value:'Lessor'}});
assert.equal(state.guidedItems[0].fields.asset_owner,'Lessor');
handler({target:{tagName:'INPUT',dataset:{g:'0',t:'term-ijara'},checked:false}});
assert.equal(state.guidedItems[0].terms.length,0);
console.log('PASS guided domain change, rerender, field preservation, explicit term/field edits');
