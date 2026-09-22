import { useEffect, useMemo, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { AlertCircle, Download, FileSearch, ListChecks, Lock, Save, Upload, UserRound } from 'lucide-react'
import './App.css'

type View = 'solicitante' | 'revision'
type DocType = 'ine' | 'acta'

type Address = {
  cp: string
  calle: string
  numeroExterior: string
  numeroInterior: string
  colonia: string
  municipio: string
  estado: string
}

type PersonName = {
  apellidoPaterno: string
  apellidoMaterno: string
  nombres: string
}

type Reference = {
  nombre: string
  nombrePartes: PersonName
  domicilio: Address
  parentesco: string
}

type CaptureForm = {
  rfc: string
  curp: string
  nombrePartes: PersonName
  nombreCompleto: string
  fechaNacimiento: string
  lugarNacimiento: string
  sexo: string
  correoElectronico: string
  telefono: string
  estadoCivil: string
  conyugeNombrePartes: PersonName
  nombreConyuge: string
  domicilio: Address
  padreNombrePartes: PersonName
  padre: string
  madreNombrePartes: PersonName
  madre: string
  noActa: string
  anioActa: string
  libro: string
  clase: string
  cartillaSmn: string
  claveCobro: string
  descripcionClave: string
  lugar: string
  fechaFiliacion: string
  referencias: Reference[]
  rasgos: {
    tonoPiel: string
    pelo: string
    frente: string
    cejas: string
    ojos: string
    nariz: string
    boca: string
    estatura: string
    senasVisibles: string
  }
}

type CpOption = {
  asentamiento: string
  municipio: string
  estado: string
  ciudad?: string
}

type Solicitud = {
  id: string
  estado: string
  curp?: string | null
  nombre_completo?: string | null
  correo_electronico?: string | null
  datos: Partial<CaptureForm>
  extracciones?: any[]
  notas_operador?: string | null
  revisado_por?: string | null
  revisado_at?: string | null
  created_at: string
}

const emptyAddress: Address = {
  cp: '',
  calle: '',
  numeroExterior: '',
  numeroInterior: '',
  colonia: '',
  municipio: '',
  estado: '',
}

const emptyName: PersonName = {
  apellidoPaterno: '',
  apellidoMaterno: '',
  nombres: '',
}

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

function cleanUpper(value: string) {
  return value.replace(/\s+/g, ' ').trim().toUpperCase()
}

function composeName(value: PersonName) {
  return [value.apellidoPaterno, value.apellidoMaterno, value.nombres]
    .map(cleanUpper)
    .filter(Boolean)
    .join(' ')
}

function splitStoredName(value?: string | null): PersonName {
  const parts = cleanUpper(value ?? '').split(' ').filter(Boolean)
  if (parts.length >= 3) {
    return {
      apellidoPaterno: parts[0],
      apellidoMaterno: parts[1],
      nombres: parts.slice(2).join(' '),
    }
  }
  return { ...emptyName, nombres: cleanUpper(value ?? '') }
}

function mergeName(parts?: Partial<PersonName>, fullName?: string | null): PersonName {
  const fallback = splitStoredName(fullName)
  return {
    apellidoPaterno: parts?.apellidoPaterno ?? fallback.apellidoPaterno,
    apellidoMaterno: parts?.apellidoMaterno ?? fallback.apellidoMaterno,
    nombres: parts?.nombres ?? fallback.nombres,
  }
}

const emptyForm: CaptureForm = {
  rfc: '',
  curp: '',
  nombrePartes: { ...emptyName },
  nombreCompleto: '',
  fechaNacimiento: '',
  lugarNacimiento: '',
  sexo: '',
  correoElectronico: '',
  telefono: '',
  estadoCivil: '',
  conyugeNombrePartes: { ...emptyName },
  nombreConyuge: '',
  domicilio: { ...emptyAddress },
  padreNombrePartes: { ...emptyName },
  padre: '',
  madreNombrePartes: { ...emptyName },
  madre: '',
  noActa: '',
  anioActa: '',
  libro: '',
  clase: '',
  cartillaSmn: '',
  claveCobro: '',
  descripcionClave: '',
  lugar: 'TOLUCA, MEXICO',
  fechaFiliacion: todayIso(),
  referencias: [
    { nombre: '', nombrePartes: { ...emptyName }, domicilio: { ...emptyAddress }, parentesco: 'Conocido' },
    { nombre: '', nombrePartes: { ...emptyName }, domicilio: { ...emptyAddress }, parentesco: 'Conocido' },
    { nombre: '', nombrePartes: { ...emptyName }, domicilio: { ...emptyAddress }, parentesco: 'Familiar' },
    { nombre: '', nombrePartes: { ...emptyName }, domicilio: { ...emptyAddress }, parentesco: 'Familiar' },
  ],
  rasgos: {
    tonoPiel: '',
    pelo: '',
    frente: '',
    cejas: '',
    ojos: '',
    nariz: '',
    boca: '',
    estatura: '',
    senasVisibles: '',
  },
}

function mergeForm(data?: Partial<CaptureForm>): CaptureForm {
  const merged = { ...emptyForm, ...(data ?? {}) }
  const nombrePartes = mergeName(merged.nombrePartes, merged.nombreCompleto)
  const conyugeNombrePartes = mergeName(merged.conyugeNombrePartes, merged.nombreConyuge)
  const padreNombrePartes = mergeName(merged.padreNombrePartes, merged.padre)
  const madreNombrePartes = mergeName(merged.madreNombrePartes, merged.madre)
  return {
    ...merged,
    nombrePartes,
    nombreCompleto: composeName(nombrePartes) || merged.nombreCompleto || '',
    conyugeNombrePartes,
    nombreConyuge: composeName(conyugeNombrePartes) || merged.nombreConyuge || '',
    padreNombrePartes,
    padre: composeName(padreNombrePartes) || merged.padre || '',
    madreNombrePartes,
    madre: composeName(madreNombrePartes) || merged.madre || '',
    domicilio: { ...emptyAddress, ...(merged.domicilio ?? {}) },
    referencias: emptyForm.referencias.map((item, index) => {
      const reference = { ...item, ...(merged.referencias?.[index] ?? {}) }
      const nombrePartes = mergeName(reference.nombrePartes, reference.nombre)
      return {
        ...reference,
        nombrePartes,
        nombre: composeName(nombrePartes) || reference.nombre || '',
        domicilio: { ...emptyAddress, ...(merged.referencias?.[index]?.domicilio ?? {}) },
      }
    }),
    rasgos: { ...emptyForm.rasgos, ...(merged.rasgos ?? {}) },
  }
}

function normalizeDate(value?: string | null) {
  if (!value) return ''
  const match = value.match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
  return match ? `${match[3]}-${match[2]}-${match[1]}` : value
}

function extractYear(value?: string | number | null) {
  const match = String(value ?? '').match(/\b(19|20)\d{2}\b/)
  return match ? match[0] : ''
}

function parseIneAddress(value?: string | null, cp?: string | null): Address {
  const address = { ...emptyAddress, cp: cp ?? '' }
  if (!value) return address
  const text = value.replace(/\s+/g, ' ').trim()
  const streetMatch = text.match(/^(.+?)\s+(?:NO\.?|NUM\.?|#)?\s*(\d+[A-Z]?)\b/i)
  if (streetMatch) {
    address.calle = streetMatch[1].trim()
    address.numeroExterior = streetMatch[2].trim()
  } else {
    address.calle = text
  }
  return address
}

function applyExtraction(current: CaptureForm, tipo: DocType, raw: any): CaptureForm {
  const datos = raw?.resultado?.datos ?? {}
  if (tipo === 'ine') {
    const extractedName = datos.nombre || ''
    const nombrePartes = current.nombreCompleto ? current.nombrePartes : splitStoredName(extractedName)
    return {
      ...current,
      curp: current.curp || datos.curp || '',
      nombrePartes,
      nombreCompleto: current.nombreCompleto || composeName(nombrePartes) || extractedName,
      fechaNacimiento: current.fechaNacimiento || normalizeDate(datos.fecha_nacimiento),
      sexo: current.sexo || datos.sexo || '',
      domicilio: current.domicilio.cp ? current.domicilio : parseIneAddress(datos.domicilio, datos.codigo_postal),
    }
  }

  const persona = datos.persona_registrada ?? {}
  const registro = datos.registro ?? {}
  const filiacion = Array.isArray(datos.filiacion) ? datos.filiacion : []
  const currentYear = /^\d{4}$/.test(current.anioActa) ? current.anioActa : ''
  const extractedYear = extractYear(registro.fecha_registro)
  const extractedName = persona.nombre_completo || ''
  const nombrePartes = current.nombreCompleto ? current.nombrePartes : splitStoredName(extractedName)
  const padreNombrePartes = current.padre ? current.padreNombrePartes : splitStoredName(filiacion[0]?.nombre_completo)
  const madreNombrePartes = current.madre ? current.madreNombrePartes : splitStoredName(filiacion[1]?.nombre_completo)
  return {
    ...current,
    curp: current.curp || datos.curp || persona.curp || '',
    nombrePartes,
    nombreCompleto: current.nombreCompleto || composeName(nombrePartes) || extractedName,
    fechaNacimiento: current.fechaNacimiento || normalizeDate(persona.fecha_nacimiento),
    lugarNacimiento: current.lugarNacimiento || persona.lugar_nacimiento?.texto || '',
    sexo: current.sexo || persona.sexo || '',
    padreNombrePartes,
    padre: current.padre || composeName(padreNombrePartes) || filiacion[0]?.nombre_completo || '',
    madreNombrePartes,
    madre: current.madre || composeName(madreNombrePartes) || filiacion[1]?.nombre_completo || '',
    noActa: current.noActa || registro.numero_acta || '',
    anioActa: currentYear || extractedYear,
    libro: current.libro || registro.libro || '',
    lugar: current.lugar || 'TOLUCA, MEXICO',
    fechaFiliacion: current.fechaFiliacion || todayIso(),
  }
}

async function readApiResponse(response: Response) {
  const text = await response.text()
  if (!text) return {}
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text }
  }
}

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

async function lookupCp(cp: string): Promise<CpOption[]> {
  if (!/^\d{5}$/.test(cp)) return []
  const response = await fetch(`/api/codigos-postales/${cp}`)
  const payload = await readApiResponse(response)
  if (!response.ok) throw new Error(payload.detail ?? 'No se pudo consultar el CP.')
  return payload.opciones ?? []
}

function AddressFields({ value, onChange, label }: { value: Address; onChange: (value: Address) => void; label: string }) {
  const [options, setOptions] = useState<CpOption[]>([])
  const [cpError, setCpError] = useState('')
  const [loadingCp, setLoadingCp] = useState(false)
  const selectedOptionIndex = options.findIndex(
    (option) =>
      option.asentamiento === value.colonia &&
      option.municipio === value.municipio &&
      option.estado === value.estado,
  )

  function update(field: keyof Address, next: string) {
    const nextValue = { ...value, [field]: next }
    if (field === 'cp') {
      setOptions([])
      setCpError('')
      nextValue.colonia = ''
      nextValue.municipio = ''
      nextValue.estado = ''
    }
    onChange(nextValue)
  }

  async function search() {
    setCpError('')
    if (!/^\d{5}$/.test(value.cp)) {
      setOptions([])
      setCpError('Escribe un CP de 5 digitos.')
      return
    }
    setLoadingCp(true)
    try {
      const found = await lookupCp(value.cp)
      setOptions(found)
      if (found.length === 1) applyOption(found[0])
      if (found.length === 0) setCpError('CP sin coincidencias en catalogo.')
    } catch (error) {
      setCpError(error instanceof Error ? error.message : 'No se pudo consultar el CP.')
    } finally {
      setLoadingCp(false)
    }
  }

  function applyOption(option: CpOption) {
    onChange({
      ...value,
      colonia: option.asentamiento,
      municipio: option.municipio,
      estado: option.estado,
    })
  }

  return (
    <fieldset className="address-block">
      <legend>{label}</legend>
      <div className="cp-search">
        <label>CP<input value={value.cp} maxLength={5} onChange={(event) => update('cp', event.target.value.replace(/\D/g, ''))} onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            search()
          }
        }} /></label>
        <button className="lookup-button" type="button" onClick={search} disabled={loadingCp || value.cp.length !== 5}>
          {loadingCp ? 'Buscando...' : 'Buscar CP'}
        </button>
      </div>
      <label>Calle<input value={value.calle} onChange={(event) => update('calle', event.target.value)} /></label>
      <label>No. exterior<input value={value.numeroExterior} onChange={(event) => update('numeroExterior', event.target.value)} /></label>
      <label>No. interior<input value={value.numeroInterior} onChange={(event) => update('numeroInterior', event.target.value)} /></label>
      <label className="colony-select">Colonia o delegacion
        <select
          value={selectedOptionIndex >= 0 ? String(selectedOptionIndex) : ''}
          disabled={options.length === 0}
          onChange={(event) => applyOption(options[Number(event.target.value)])}
        >
          <option value="">{options.length ? 'Selecciona colonia' : ''}</option>
          {options.map((option, index) => (
            <option value={index} key={`${option.asentamiento}-${index}`}>
              {option.asentamiento}
            </option>
          ))}
        </select>
      </label>
      <label>Municipio<input value={value.municipio} onChange={(event) => update('municipio', event.target.value)} /></label>
      <label>Estado<input value={value.estado} onChange={(event) => update('estado', event.target.value)} /></label>
      {cpError && <p className="field-error">{cpError}</p>}
    </fieldset>
  )
}

function NameFields({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string
  value: PersonName
  onChange: (value: PersonName, fullName: string) => void
  disabled?: boolean
}) {
  function update(field: keyof PersonName, next: string) {
    if (disabled) return
    const nextValue = { ...value, [field]: next.toUpperCase() }
    onChange(nextValue, composeName(nextValue))
  }

  return (
    <fieldset className="name-block">
      <legend>{label}</legend>
      <label>Apellido paterno<input disabled={disabled} value={value.apellidoPaterno} onChange={(event) => update('apellidoPaterno', event.target.value)} /></label>
      <label>Apellido materno<input disabled={disabled} value={value.apellidoMaterno} onChange={(event) => update('apellidoMaterno', event.target.value)} /></label>
      <label>Nombre(s)<input disabled={disabled} value={value.nombres} onChange={(event) => update('nombres', event.target.value)} /></label>
    </fieldset>
  )
}

function CivilStatusFields({
  estadoCivil,
  conyuge,
  conyugePartes,
  onEstadoCivil,
  onConyuge,
}: {
  estadoCivil: string
  conyuge: string
  conyugePartes: PersonName
  onEstadoCivil: (value: string) => void
  onConyuge: (parts: PersonName, fullName: string) => void
}) {
  const normalized = estadoCivil.toLowerCase()
  const spouseEnabled = !['', 'soltero', 'soltera'].includes(normalized)

  function updateCivilStatus(value: string) {
    onEstadoCivil(value)
    if (['', 'Soltero', 'Soltera'].includes(value)) {
      onConyuge({ ...emptyName }, '')
    }
  }

  return (
    <>
      <label>Estado civil
        <select value={estadoCivil} onChange={(event) => updateCivilStatus(event.target.value)}>
          <option value="">Selecciona</option>
          <option value="Soltero">Soltero</option>
          <option value="Soltera">Soltera</option>
          <option value="Casado">Casado</option>
          <option value="Casada">Casada</option>
          <option value="Union libre">Union libre</option>
        </select>
      </label>
      <div className={`spouse-name-wrapper ${!spouseEnabled ? 'disabled-name-block' : ''}`}>
        <NameFields
          label="Nombre del conyuge"
          value={spouseEnabled ? conyugePartes : mergeName(undefined, conyuge)}
          onChange={onConyuge}
          disabled={!spouseEnabled}
        />
      </div>
    </>
  )
}

function App() {
  const view: View = window.location.pathname.replace(/\/$/, '') === '/revision' ? 'revision' : 'solicitante'
  const [requestForm, setRequestForm] = useState<CaptureForm>(mergeForm())
  const [operatorForm, setOperatorForm] = useState<CaptureForm>(mergeForm())
  const [operatorNotes, setOperatorNotes] = useState('')
  const [token, setToken] = useState(() => localStorage.getItem('revisionToken') ?? '')
  const [username, setUsername] = useState(() => localStorage.getItem('revisionUser') ?? '')
  const [login, setLogin] = useState({ username: '', password: '' })
  const [solicitudes, setSolicitudes] = useState<Solicitud[]>([])
  const [selected, setSelected] = useState<Solicitud | null>(null)
  const [tipo, setTipo] = useState<DocType>('ine')
  const [pagina, setPagina] = useState(1)
  const [file, setFile] = useState<File | null>(null)
  const [lastExtraction, setLastExtraction] = useState<any>(null)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const warnings = useMemo(() => {
    const value = lastExtraction?.resultado?.advertencias
    return Array.isArray(value) ? value : []
  }, [lastExtraction])

  useEffect(() => {
    if (view === 'revision' && token) loadSolicitudes()
  }, [view, token])

  function setRequestField<K extends keyof CaptureForm>(field: K, value: CaptureForm[K]) {
    setRequestForm((current) => ({ ...current, [field]: value }))
  }

  function setOperatorField<K extends keyof CaptureForm>(field: K, value: CaptureForm[K]) {
    setOperatorForm((current) => ({ ...current, [field]: value }))
  }

  function updateReference(index: number, field: 'nombre' | 'nombrePartes' | 'domicilio', value: string | PersonName | Address) {
    setRequestForm((current) => ({
      ...current,
      referencias: current.referencias.map((reference, i) =>
        i === index ? { ...reference, [field]: value } : reference,
      ),
    }))
  }

  function updateOperatorReference(index: number, field: 'nombre' | 'nombrePartes' | 'domicilio', value: string | PersonName | Address) {
    setOperatorForm((current) => ({
      ...current,
      referencias: current.referencias.map((reference, i) =>
        i === index ? { ...reference, [field]: value } : reference,
      ),
    }))
  }

  async function submitSolicitud() {
    setSaving(true)
    setError('')
    const response = await fetch('/api/solicitudes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        estado: 'enviada',
        curp: requestForm.curp || null,
        nombre_completo: requestForm.nombreCompleto || null,
        correo_electronico: requestForm.correoElectronico || null,
        datos: requestForm,
        extracciones: [],
      }),
    })
    const payload = await readApiResponse(response)
    setSaving(false)
    if (!response.ok) {
      setError(payload.detail ?? 'No se pudo enviar la solicitud.')
      return
    }
    setRequestForm(mergeForm())
    setStatus(`Solicitud enviada. Folio tecnico: ${payload.id}`)
  }

  async function loginOperator(event: FormEvent) {
    event.preventDefault()
    setError('')
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(login),
    })
    const payload = await readApiResponse(response)
    if (!response.ok) {
      setError(payload.detail ?? 'No se pudo iniciar sesion.')
      return
    }
    localStorage.setItem('revisionToken', payload.token)
    localStorage.setItem('revisionUser', payload.username)
    setToken(payload.token)
    setUsername(payload.username)
    setStatus(`Sesión iniciada como ${payload.username}`)
  }

  async function loadSolicitudes() {
    setError('')
    const response = await fetch('/api/solicitudes', { headers: authHeaders(token) })
    const payload = await readApiResponse(response)
    if (!response.ok) {
      setError(payload.detail ?? 'No se pudieron cargar solicitudes.')
      return
    }
    setSolicitudes(payload)
    if (payload.length && !selected) selectSolicitud(payload[0])
  }

  function selectSolicitud(solicitud: Solicitud) {
    setSelected(solicitud)
    setOperatorForm(mergeForm(solicitud.datos))
    setOperatorNotes(solicitud.notas_operador ?? '')
    setLastExtraction(null)
    setFile(null)
  }

  async function handleExtraction(event: FormEvent) {
    event.preventDefault()
    if (!file) {
      setError('Selecciona una imagen o PDF.')
      return
    }

    setStatus('Analizando documento...')
    setError('')

    const body = new FormData()
    body.append('tipo', tipo)
    body.append('pagina', String(pagina))
    body.append('archivo', file)

    const response = await fetch('/api/extracciones', {
      method: 'POST',
      headers: authHeaders(token),
      body,
    })
    const payload = await readApiResponse(response)
    if (!response.ok) {
      setStatus('')
      setError(payload.detail ?? 'No se pudo analizar el documento.')
      return
    }
    setLastExtraction(payload)
    setOperatorForm((current) => applyExtraction(current, tipo, payload))
    setStatus('Extracción aplicada al formulario de revision.')
  }

  async function saveReview() {
    if (!selected) return
    setSaving(true)
    setError('')
    const extracciones = lastExtraction ? [...(selected.extracciones ?? []), lastExtraction] : selected.extracciones ?? []
    const response = await fetch(`/api/solicitudes/${selected.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
      body: JSON.stringify({
        estado: 'revisada',
        curp: operatorForm.curp || null,
        nombre_completo: operatorForm.nombreCompleto || null,
        correo_electronico: operatorForm.correoElectronico || null,
        datos: operatorForm,
        extracciones,
        notas_operador: operatorNotes,
      }),
    })
    const payload = await readApiResponse(response)
    setSaving(false)
    if (!response.ok) {
      setError(payload.detail ?? 'No se pudo guardar la revision.')
      return
    }
    setStatus(`Revisión guardada por ${payload.revisado_por}`)
    setSelected(payload)
    setSolicitudes((items) => items.map((item) => (item.id === payload.id ? payload : item)))
  }

  async function downloadExcel() {
    if (!selected) return
    setError('')
    const response = await fetch(`/api/solicitudes/${selected.id}/excel`, {
      headers: authHeaders(token),
    })
    if (!response.ok) {
      const payload = await readApiResponse(response)
      setError(payload.detail ?? 'No se pudo generar el Excel.')
      return
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `filiacion_${operatorForm.curp || selected.id}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <main className="app-shell">
      <section className={`workspace ${view}-workspace`}>
        <header className="topbar">
          <div>
            <p className="eyebrow">{view === 'solicitante' ? 'Inicio de solicitud' : 'Panel de revision'}</p>
            <h1>{view === 'solicitante' ? 'Solicitud de filiacion' : 'Revisión de solicitudes'}</h1>
          </div>
          {view === 'revision' && token && <span className="operator-badge"><Lock size={16} /> {username}</span>}
        </header>

        {error && <p className="error"><AlertCircle size={17} />{error}</p>}
        {status && <p className="notice">{status}</p>}

        {view === 'solicitante' ? (
          <SolicitanteForm
            form={requestForm}
            setField={setRequestField}
            setAddress={(domicilio) => setRequestField('domicilio', domicilio)}
            updateReference={updateReference}
            saving={saving}
            onSubmit={submitSolicitud}
          />
        ) : !token ? (
          <form className="login-panel" onSubmit={loginOperator}>
            <div className="section-title"><Lock size={20} /><h2>Acceso de revisión</h2></div>
            <label>Usuario<input value={login.username} onChange={(event) => setLogin({ ...login, username: event.target.value })} /></label>
            <label>Contraseña<input type="password" value={login.password} onChange={(event) => setLogin({ ...login, password: event.target.value })} /></label>
            <button className="primary" type="submit">Entrar</button>
          </form>
        ) : (
          <section className="operator-grid">
            <div className="requests-list">
              <div className="section-title"><ListChecks size={20} /><h2>Solicitudes</h2></div>
              <button className="secondary" type="button" onClick={loadSolicitudes}>Actualizar lista</button>
              {solicitudes.map((solicitud) => (
                <button className={selected?.id === solicitud.id ? 'request selected' : 'request'} key={solicitud.id} onClick={() => selectSolicitud(solicitud)}>
                  <strong>{solicitud.nombre_completo || solicitud.datos?.nombreCompleto || 'Sin nombre'}</strong>
                  <span>{solicitud.estado}</span>
                  <small>{new Date(solicitud.created_at).toLocaleString()}</small>
                </button>
              ))}
            </div>

            <div className="review-panel">
              {selected ? (
                <>
                  <section className="document-panel">
                    <form className="upload-panel" onSubmit={handleExtraction}>
                      <div className="section-title"><FileSearch size={20} /><h2>Análisis de documentos</h2></div>
                      <div className="segmented">
                        <button type="button" className={tipo === 'ine' ? 'selected' : ''} onClick={() => setTipo('ine')}>INE</button>
                        <button type="button" className={tipo === 'acta' ? 'selected' : ''} onClick={() => setTipo('acta')}>Acta</button>
                      </div>
                      <label className="file-drop">
                        <Upload size={22} />
                        <span>{file ? file.name : 'Imagen o PDF recibido'}</span>
                        <input type="file" accept=".jpg,.jpeg,.png,.bmp,.tif,.tiff,.webp,.pdf" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} />
                      </label>
                      {tipo === 'ine' && <label className="inline-label">Pagina PDF<input type="number" min="1" value={pagina} onChange={(event) => setPagina(Number(event.target.value))} /></label>}
                      <button className="secondary" type="submit"><FileSearch size={18} />Analizar documento</button>
                      {warnings.length > 0 && <ul className="warnings">{warnings.map((warning: string, index: number) => <li key={index}>{warning}</li>)}</ul>}
                    </form>
                  </section>

                  <FullFiliacionForm
                    form={operatorForm}
                    setField={setOperatorField}
                    updateReference={updateOperatorReference}
                    notes={operatorNotes}
                    setNotes={setOperatorNotes}
                    onSave={saveReview}
                    onDownloadExcel={downloadExcel}
                    saving={saving}
                  />
                </>
              ) : (
                <p className="notice">Selecciona una solicitud.</p>
              )}
            </div>
          </section>
        )}
      </section>
    </main>
  )
}

function SolicitanteForm({
  form,
  setField,
  setAddress,
  updateReference,
  saving,
  onSubmit,
}: {
  form: CaptureForm
  setField: <K extends keyof CaptureForm>(field: K, value: CaptureForm[K]) => void
  setAddress: (value: Address) => void
  updateReference: (index: number, field: 'nombre' | 'nombrePartes' | 'domicilio', value: string | PersonName | Address) => void
  saving: boolean
  onSubmit: () => void
}) {
  return (
    <>
      <section className="form-section">
        <div className="section-title"><UserRound size={20} /><h2>Datos del solicitante</h2></div>
        <NameFields
          label="Nombre del solicitante"
          value={form.nombrePartes}
          onChange={(parts, fullName) => {
            setField('nombrePartes', parts)
            setField('nombreCompleto', fullName)
          }}
        />
        <div className="form-grid four">
          <label>RFC<input value={form.rfc} onChange={(event) => setField('rfc', event.target.value.toUpperCase())} /></label>
          <label>Telefono<input value={form.telefono} onChange={(event) => setField('telefono', event.target.value)} /></label>
          <label>Correo electronico<input type="email" value={form.correoElectronico} onChange={(event) => setField('correoElectronico', event.target.value)} /></label>
          <CivilStatusFields
            estadoCivil={form.estadoCivil}
            conyuge={form.nombreConyuge}
            conyugePartes={form.conyugeNombrePartes}
            onEstadoCivil={(value) => setField('estadoCivil', value)}
            onConyuge={(parts, fullName) => {
              setField('conyugeNombrePartes', parts)
              setField('nombreConyuge', fullName)
            }}
          />
        </div>
      </section>

      <section className="form-section">
        <AddressFields label="Domicilio particular" value={form.domicilio} onChange={setAddress} />
      </section>

      <section className="references">
        <div className="section-title"><h2>Referencias</h2></div>
        <div className="reference-grid">
          {form.referencias.map((reference, index) => (
            <div className="reference-item" key={index}>
              <strong>{reference.parentesco} {index + 1}</strong>
              <NameFields
                label="Nombre"
                value={reference.nombrePartes}
                onChange={(parts, fullName) => {
                  updateReference(index, 'nombrePartes', parts)
                  updateReference(index, 'nombre', fullName)
                }}
              />
              <AddressFields label="Domicilio" value={reference.domicilio} onChange={(domicilio) => updateReference(index, 'domicilio', domicilio)} />
            </div>
          ))}
        </div>
      </section>

      <div className="actions-row">
        <button className="primary" type="button" onClick={onSubmit} disabled={saving}><Save size={18} />{saving ? 'Enviando...' : 'Enviar solicitud'}</button>
      </div>
    </>
  )
}

function FullFiliacionForm({
  form,
  setField,
  updateReference,
  notes,
  setNotes,
  onSave,
  onDownloadExcel,
  saving,
}: {
  form: CaptureForm
  setField: <K extends keyof CaptureForm>(field: K, value: CaptureForm[K]) => void
  updateReference: (index: number, field: 'nombre' | 'nombrePartes' | 'domicilio', value: string | PersonName | Address) => void
  notes: string
  setNotes: (value: string) => void
  onSave: () => void
  onDownloadExcel: () => void
  saving: boolean
}) {
  const rasgoOptions: Record<keyof CaptureForm['rasgos'], string[]> = {
    tonoPiel: ['Claro', 'Mediano', 'Obscuro'],
    pelo: ['Castano claro', 'Castano oscuro', 'Negro', 'Cano', 'Calvo', 'Ninguna'],
    frente: ['Pequena', 'Mediana', 'Grande'],
    cejas: ['Abundantes', 'Regulares', 'Escasas'],
    ojos: ['Castano oscuro', 'Castano claro', 'Pardos', 'Verdosos', 'Azules'],
    nariz: ['Concava', 'Convexa', 'Rectilinea'],
    boca: ['Pequena', 'Regular', 'Grande'],
    estatura: [],
    senasVisibles: [],
  }

  return (
    <>
      <section className="form-section">
        <div className="section-title"><h2>Datos administrativos</h2></div>
        <div className="form-grid four">
          <label>Filiacion / RFC<input value={form.rfc} onChange={(event) => setField('rfc', event.target.value.toUpperCase())} /></label>
          <label>CURP<input value={form.curp} onChange={(event) => setField('curp', event.target.value.toUpperCase())} /></label>
          <label>Clave de cobro<input value={form.claveCobro} onChange={(event) => setField('claveCobro', event.target.value)} /></label>
          <label>Descripcion de la clave<input value={form.descripcionClave} onChange={(event) => setField('descripcionClave', event.target.value)} /></label>
          <label>Lugar<input value={form.lugar} onChange={(event) => setField('lugar', event.target.value.toUpperCase())} /></label>
          <label>Fecha<input type="date" value={form.fechaFiliacion} onChange={(event) => setField('fechaFiliacion', event.target.value)} /></label>
        </div>
      </section>

      <section className="form-section">
        <div className="section-title"><h2>Identidad y registro civil</h2></div>
        <NameFields
          label="Nombre"
          value={form.nombrePartes}
          onChange={(parts, fullName) => {
            setField('nombrePartes', parts)
            setField('nombreCompleto', fullName)
          }}
        />
        <div className="form-grid four">
          <label>Fecha nacimiento<input type="date" value={form.fechaNacimiento} onChange={(event) => setField('fechaNacimiento', event.target.value)} /></label>
          <label>Lugar nacimiento<input value={form.lugarNacimiento} onChange={(event) => setField('lugarNacimiento', event.target.value)} /></label>
          <label>Sexo<input value={form.sexo} onChange={(event) => setField('sexo', event.target.value)} /></label>
          <label>No. acta<input value={form.noActa} onChange={(event) => setField('noActa', event.target.value)} /></label>
          <label>Anio<input value={form.anioActa} maxLength={4} onChange={(event) => setField('anioActa', event.target.value.replace(/\D/g, '').slice(0, 4))} /></label>
          <label>Libro<input value={form.libro} onChange={(event) => setField('libro', event.target.value)} /></label>
          <label>Clase<input value={form.clase} onChange={(event) => setField('clase', event.target.value)} /></label>
          <label>Cartilla S.M.N.<input value={form.cartillaSmn} onChange={(event) => setField('cartillaSmn', event.target.value)} /></label>
        </div>
        <div className="form-grid two name-pair-grid">
          <NameFields
            label="Nombre del padre"
            value={form.padreNombrePartes}
            onChange={(parts, fullName) => {
              setField('padreNombrePartes', parts)
              setField('padre', fullName)
            }}
          />
          <NameFields
            label="Nombre de la madre"
            value={form.madreNombrePartes}
            onChange={(parts, fullName) => {
              setField('madreNombrePartes', parts)
              setField('madre', fullName)
            }}
          />
        </div>
      </section>

      <section className="form-section">
        <div className="section-title"><h2>Estado civil y contacto</h2></div>
        <div className="form-grid four">
          <CivilStatusFields
            estadoCivil={form.estadoCivil}
            conyuge={form.nombreConyuge}
            conyugePartes={form.conyugeNombrePartes}
            onEstadoCivil={(value) => setField('estadoCivil', value)}
            onConyuge={(parts, fullName) => {
              setField('conyugeNombrePartes', parts)
              setField('nombreConyuge', fullName)
            }}
          />
          <label>Correo electronico<input value={form.correoElectronico} onChange={(event) => setField('correoElectronico', event.target.value)} /></label>
          <label>Telefono<input value={form.telefono} onChange={(event) => setField('telefono', event.target.value)} /></label>
        </div>
      </section>

      <section className="form-section">
        <AddressFields label="Domicilio" value={form.domicilio} onChange={(domicilio) => setField('domicilio', domicilio)} />
      </section>

      <section className="references">
        <div className="section-title"><h2>Referencias</h2></div>
        <div className="reference-grid">
          {form.referencias.map((reference, index) => (
            <div className="reference-item" key={index}>
              <strong>{reference.parentesco} {index + 1}</strong>
              <NameFields
                label="Nombre"
                value={reference.nombrePartes}
                onChange={(parts, fullName) => {
                  updateReference(index, 'nombrePartes', parts)
                  updateReference(index, 'nombre', fullName)
                }}
              />
              <AddressFields label="Domicilio" value={reference.domicilio} onChange={(domicilio) => updateReference(index, 'domicilio', domicilio)} />
            </div>
          ))}
        </div>
      </section>

      <section className="form-section">
        <div className="section-title"><h2>Rasgos fisicos</h2></div>
        <div className="form-grid four">
          {Object.entries(form.rasgos).map(([key, value]) => (
            <label key={key}>
              {key}
              {rasgoOptions[key as keyof CaptureForm['rasgos']].length ? (
                <select value={value} onChange={(event) => setField('rasgos', { ...form.rasgos, [key]: event.target.value })}>
                  <option value="">Selecciona</option>
                  {rasgoOptions[key as keyof CaptureForm['rasgos']].map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              ) : (
                <input value={value} onChange={(event) => setField('rasgos', { ...form.rasgos, [key]: event.target.value })} />
              )}
            </label>
          ))}
        </div>
      </section>

      <section className="form-section">
        <div className="section-title"><h2>Notas de revision</h2></div>
        <label className="notes-label">Notas de revisión<textarea value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
      </section>

      <div className="actions-row">
        <button className="secondary" type="button" onClick={onDownloadExcel}><Download size={18} />Descargar Excel</button>
        <button className="primary" type="button" onClick={onSave} disabled={saving}><Save size={18} />{saving ? 'Guardando...' : 'Guardar revision'}</button>
      </div>
    </>
  )
}

export default App
