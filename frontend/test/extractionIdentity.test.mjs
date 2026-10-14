import { test } from 'node:test'
import assert from 'node:assert/strict'
import { actaIdentityConflict } from '../src/extractionIdentity.ts'

test('accepts accents and names stored surname first', () => {
  assert.equal(actaIdentityConflict({ nombreCompleto: 'LOPEZ PEREZ MARIA ELENA', curp: '' }, {
    persona_registrada: { nombre_completo: 'MAR\u00cdA ELENA L\u00d3PEZ PEREZ' },
  }), null)
})

test('blocks mixing an acta into another persons record', () => {
  assert.match(actaIdentityConflict({ nombreCompleto: 'ROSA SOTO RUIZ', curp: '' }, {
    persona_registrada: { nombre_completo: 'MARIA ELENA LOPEZ PEREZ' },
  }), /No se aplicaron datos/)
})

test('blocks conflicting CURPs even if names match', () => {
  assert.match(actaIdentityConflict({ nombreCompleto: 'MARIA LOPEZ PEREZ', curp: 'LOPM900101MDFPRS01' }, {
    curp: 'LOPM900102MDFPRS01', persona_registrada: { nombre_completo: 'MARIA LOPEZ PEREZ' },
  }), /CURP/)
})

test('allows correcting a malformed previous OCR CURP', () => {
  assert.equal(actaIdentityConflict({ nombreCompleto: '', curp: 'LOPM900101MDFPRS01 CO' }, {
    curp: 'LOPM900101MDFPRS01',
  }), null)
})
