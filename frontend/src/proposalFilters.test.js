import { describe, it, expect, vi, afterEach } from 'vitest';
import { initializeProposalFilters } from './proposalFilters.js';
function setup() {
  const control = (tagName, type) => ({ tagName, type, events: {}, addEventListener(event, fn) { this.events[event] = fn; } });
  const status = control('SELECT'); const advanced = control('SELECT'); const search = control('INPUT', 'search');
  const button = { hidden:false }; const events = {};
  const form = { elements:[status, advanced, search], requestSubmit:vi.fn(), querySelector:()=>button, addEventListener:(e,fn)=>{events[e]=fn;} };
  initializeProposalFilters({getElementById:()=>form},globalThis);
  return { status, advanced, search, button, form, events };
}
afterEach(()=>vi.useRealTimers());
describe('proposal automatic filters',()=>{
  it('applies status and externally associated advanced controls immediately',()=>{
    const {status,advanced,button,form}=setup();
    expect(button.hidden).toBe(true); status.events.change(); advanced.events.change();
    expect(form.requestSubmit).toHaveBeenCalledTimes(2);
  });
  it('debounces search and cancels pending search when a filter changes',()=>{
    vi.useFakeTimers(); const {search,status,form}=setup();
    search.events.input({}); vi.advanceTimersByTime(200); search.events.input({});
    vi.advanceTimersByTime(449); expect(form.requestSubmit).not.toHaveBeenCalled();
    status.events.change(); vi.advanceTimersByTime(500); expect(form.requestSubmit).toHaveBeenCalledTimes(1);
    search.events.input({}); vi.advanceTimersByTime(450); expect(form.requestSubmit).toHaveBeenCalledTimes(2);
  });
  it('waits for composition and cancels a pending timer on explicit submit',()=>{
    vi.useFakeTimers(); const {search,form,events}=setup();
    search.events.input({isComposing:true}); vi.advanceTimersByTime(500); expect(form.requestSubmit).not.toHaveBeenCalled();
    search.events.compositionend({}); events.submit(); vi.advanceTimersByTime(500); expect(form.requestSubmit).not.toHaveBeenCalled();
  });
});
