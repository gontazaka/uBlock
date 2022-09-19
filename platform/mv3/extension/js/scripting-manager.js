/*******************************************************************************

    uBlock Origin - a browser extension to block requests.
    Copyright (C) 2022-present Raymond Hill

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see {http://www.gnu.org/licenses/}.

    Home: https://github.com/gorhill/uBlock
*/

/* jshint esversion:11 */

'use strict';

/******************************************************************************/

import { browser, dnr } from './ext.js';
import { fetchJSON } from './fetch.js';
import { parsedURLromOrigin } from './utils.js';

/******************************************************************************/

const CSS_TYPE = '0';
const JS_TYPE = '1';

/******************************************************************************/

let scriptingDetailsPromise;

function getScriptingDetails() {
    if ( scriptingDetailsPromise !== undefined ) {
        return scriptingDetailsPromise;
    }
    scriptingDetailsPromise = fetchJSON('/rulesets/scripting-details').then(entries => {
        const out = new Map(entries);
        for ( const details of out.values() ) {
            details.matches = new Map(details.matches);
            details.excludeMatches = new Map(details.excludeMatches);
        }
        return out;
    });
    return scriptingDetailsPromise;
}

/******************************************************************************/

const matchesFromHostnames = hostnames => {
    const out = [];
    for ( const hn of hostnames ) {
        if ( hn === '*' ) {
            out.push('*://*/*');
        } else {
            out.push(`*://*.${hn}/*`);
        }
    }
    return out;
};

const hostnamesFromMatches = origins => {
    const out = [];
    for ( const origin of origins ) {
        const match = /^\*:\/\/([^\/]+)\/\*/.exec(origin);
        if ( match === null ) { continue; }
        out.push(match[1]);
    }
    return out;
};

const toBroaderHostname = hn => {
    if ( hn === '*' ) { return ''; }
    const pos = hn.indexOf('.');
    return pos !== -1 ? hn.slice(pos+1) : '*';
};

const arrayEq = (a, b) => {
    if ( a === undefined ) { return b === undefined; }
    if ( b === undefined ) { return false; }
    if ( a.length !== b.length ) { return false; }
    for ( const i of a ) {
        if ( b.includes(i) === false ) { return false; }
    }
    return true;
};

/******************************************************************************/

const toRegisterable = (fname, entry) => {
    const directive = {
        id: fname,
        allFrames: true,
    };
    if ( entry.matches ) {
        directive.matches = matchesFromHostnames(entry.matches);
    } else {
        directive.matches = [ '*://*/*' ];
    }
    if ( entry.excludeMatches ) {
        directive.excludeMatches = matchesFromHostnames(entry.excludeMatches);
    }
    if ( fname.at(-1) === CSS_TYPE ) {
        directive.css = [
            `/rulesets/css/${fname.slice(0,1)}/${fname.slice(1,2)}/${fname.slice(2)}.css`
        ];
    } else if ( fname.at(-1) === JS_TYPE ) {
        directive.js = [
            `/rulesets/js/${fname}.js`
        ];
        directive.runAt = 'document_start';
        directive.world = 'MAIN';
    }

    return directive;
};

const toMaybeUpdatable = (registered, candidate) => {
    const matches = candidate.matches &&
        matchesFromHostnames(candidate.matches);
    if ( arrayEq(registered.matches, matches) === false ) {
        return toRegisterable(candidate);
    }
    const excludeMatches = candidate.excludeMatches &&
        matchesFromHostnames(candidate.excludeMatches);
    if ( arrayEq(registered.excludeMatches, excludeMatches) === false ) {
        return toRegisterable(candidate);
    }
};

/******************************************************************************/

async function getInjectableCount(origin) {
    const url = parsedURLromOrigin(origin);
    if ( url === undefined ) { return 0; }

    const [
        rulesetIds,
        scriptingDetails,
    ] = await Promise.all([
        dnr.getEnabledRulesets(),
        getScriptingDetails(),
    ]);

    let total = 0;

    for ( const rulesetId of rulesetIds ) {
        if ( scriptingDetails.has(rulesetId) === false ) { continue; }
        const details = scriptingDetails.get(rulesetId);
        let hn = url.hostname;
        while ( hn !== '' ) {
            const fnames = details.matches.get(hn);
            total += fnames && fnames.length || 0;
            hn = toBroaderHostname(hn);
        }
    }

    return total;
}

/******************************************************************************/

// TODO: Mind trusted-site directives.

async function registerInjectable() {

    const [
        hostnames,
        rulesetIds,
        registered,
        scriptingDetails,
    ] = await Promise.all([
        browser.permissions.getAll(),
        dnr.getEnabledRulesets(),
        browser.scripting.getRegisteredContentScripts(),
        getScriptingDetails(),
    ]).then(results => {
        results[0] = new Set(hostnamesFromMatches(results[0].origins));
        return results;
    });

    if ( hostnames.has('*') && hostnames.size > 1 ) {
        hostnames.clear();
        hostnames.add('*');
    }

    const toRegister = new Map();

    const checkRealm = (details, prop, hn) => {
        const fnames = details[prop]?.get(hn);
        if ( fnames === undefined ) { return; }
        for ( const fname of fnames ) {
            const existing = toRegister.get(fname);
            if ( existing ) {
                existing[prop].push(hn);
            } else {
                toRegister.set(fname, { [prop]: [ hn ] });
            }
        }
    };

    for ( const rulesetId of rulesetIds ) {
        const details = scriptingDetails.get(rulesetId);
        if ( details === undefined ) { continue; }
        for ( let hn of hostnames ) {
            while ( hn !== '' ) {
                checkRealm(details, 'matches', hn);
                checkRealm(details, 'excludeMatches', hn);
                hn = toBroaderHostname(hn);
            }
        }
    }

    const before = new Map(registered.map(entry => [ entry.id, entry ]));

    const toAdd = [];
    const toUpdate = [];
    for ( const [ fname, entry ] of toRegister ) {
        if ( before.has(fname) === false ) {
            toAdd.push(toRegisterable(fname, entry));
            continue;
        }
        const updated = toMaybeUpdatable(before.get(fname), entry);
        if ( updated !== undefined ) {
            toUpdate.push(updated);
        }
    }

    const toRemove = [];
    for ( const fname of before.keys() ) {
        if ( toRegister.has(fname) ) { continue; }
        toRemove.push(fname);
    }

    const todo = [];
    if ( toRemove.length !== 0 ) {
        todo.push(browser.scripting.unregisterContentScripts({ ids: toRemove }));
        console.info(`Unregistered ${toRemove} content (css/js)`);
    }
    if ( toAdd.length !== 0 ) {
        todo.push(browser.scripting.registerContentScripts(toAdd));
        console.info(`Registered ${toAdd.map(v => v.id)} content (css/js)`);
    }
    if ( toUpdate.length !== 0 ) {
        todo.push(browser.scripting.updateContentScripts(toUpdate));
        console.info(`Updated ${toUpdate.map(v => v.id)} content (css/js)`);
    }
    if ( todo.length === 0 ) { return; }

    return Promise.all(todo);
}

/******************************************************************************/

export {
    getInjectableCount,
    registerInjectable
};
