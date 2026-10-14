type Identity = { nombreCompleto: string; curp: string }
type ActaIdentity = { curp?: string | null; persona_registrada?: { nombre_completo?: string | null } }

function normalizedName(value: string) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase()
    .split(/[^A-Z]+/).filter(Boolean).sort().join(' ')
}

export function actaIdentityConflict(current: Identity, datos: ActaIdentity): string | null {
  const documentName = datos.persona_registrada?.nombre_completo ?? ''
  if (current.nombreCompleto && documentName && normalizedName(current.nombreCompleto) !== normalizedName(documentName)) {
    return `El acta corresponde a ${documentName}, pero el expediente es de ${current.nombreCompleto}. No se aplicaron datos. Verifica el documento y el expediente seleccionado.`
  }
  const curpPattern = /^[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{5}[A-Z0-9]\d$/
  const currentCurp = current.curp.trim().toUpperCase()
  const documentCurp = datos.curp?.trim().toUpperCase() ?? ''
  if (curpPattern.test(currentCurp) && curpPattern.test(documentCurp) && currentCurp !== documentCurp) {
    return 'La CURP del acta no coincide con la del expediente. No se aplicaron datos. Verifica el documento y el expediente seleccionado.'
  }
  return null
}
