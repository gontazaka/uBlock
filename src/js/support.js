/*******************************************************************************

    uBlock Origin - a browser extension to block requests.
    Copyright (C) 2014-present Raymond Hill

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

/* global CodeMirror, uBlockDashboard, uDom */

'use strict';

/******************************************************************************/

let supportData;

const sensitiveValues = [
    'filterset',
    'modifiedHiddenSettings.userResourcesLocation',
    'trustedset.added',
    'hostRuleset.added',
    'switchRuleset.added',
    'urlRuleset.added',
];

const sensitiveKeys = [
    'listset.added',
];

/******************************************************************************/

function redactValue(data, prop) {
    if ( data instanceof Object === false ) { return; }
    const pos = prop.indexOf('.');
    if ( pos !== -1 ) {
        return redactValue(data[prop.slice(0, pos)], prop.slice(pos + 1));
    }
    let value = data[prop];
    if ( value === undefined ) { return; }
    if ( Array.isArray(value) ) {
        value = `[array of ${value.length} redacted]`;
    } else {
        value = '[redacted]';
    }
    data[prop] = value;
}

function redactKeys(data, prop) {
    if ( data instanceof Object === false ) { return; }
    const pos = prop.indexOf('.');
    if ( pos !== -1 ) {
        return redactKeys(data[prop.slice(0, pos)], prop.slice(pos + 1));
    }
    const obj = data[prop];
    if ( obj instanceof Object === false ) { return; }
    let count = 1;
    for ( const key in obj ) {
        if ( key.startsWith('file://') === false ) { continue; }
        const newkey = `[list name ${count} redacted]`;
        obj[newkey] = obj[key];
        obj[key] = undefined; 
        count += 1;
    }
}

function showData() {
    const shownData = JSON.parse(JSON.stringify(supportData));
    if ( document.body.classList.contains('redacted') ) {
        sensitiveValues.forEach(prop => { redactValue(shownData, prop); });
        sensitiveKeys.forEach(prop => { redactKeys(shownData, prop); });

        // Redact list entries which could be hosted locally
        
    }
    const text = JSON.stringify(shownData, null, 2)
        .split('\n')
        .slice(1, -1)
        .map(v => {
            return v
                .replace( /^(   *)"/, '  $1')
                .replace( /^( +.*[^\\])(?:": "|": \{$|": \[$|": )/, '$1: ')
                .replace( /(?:"|"|\}|\]),?$/, '');
        })
        .filter(v => v.trim() !== '')
        .join('\n');
    cmEditor.setValue(text + '\n');
    cmEditor.clearHistory();
}

/******************************************************************************/

const cmEditor = new CodeMirror(document.getElementById('supportData'), {
    autofocus: true,
    lineWrapping: true,
    styleActiveLine: true,
});

uBlockDashboard.patchCodeMirrorEditor(cmEditor);

/******************************************************************************/

(async ( ) => {
    supportData = await vAPI.messaging.send('dashboard', {
        what: 'getSupportData',
    });

    // Remove unnecessary information
    if ( supportData.modifiedHiddenSettings instanceof Object ) {
        const o = supportData.modifiedHiddenSettings;
        o.benchmarkDatasetURL = undefined;
    }

    showData();

    uDom('[data-url]').on('click', ev => {
        const url = ev.target.getAttribute('data-url');
        if ( typeof url !== 'string' || url === '' ) { return; }
        vAPI.messaging.send('default', {
            what: 'gotoURL',
            details: { url, select: true },
        });
        ev.preventDefault();
    });

    uDom('#redactButton').on('click', ( ) => {
        document.body.classList.add('redacted');
        showData();
    });

    uDom('#unredactButton').on('click', ( ) => {
        document.body.classList.remove('redacted');
        showData();
    });

    uDom('#selectAllButton').on('click', ( ) => {
        cmEditor.execCommand('selectAll');
    });
})();
