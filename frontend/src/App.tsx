import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { AlertCircle, ArrowLeft, ArrowUpRight, Camera, Check, ChevronRight, Download, FileSearch, Info, ListChecks, Lock, QrCode, RefreshCw, RotateCcw, Save, Trash2, Upload } from 'lucide-react'
import './App.css'

type View = 'solicitante' | 'revision'
type DocType = 'ine' | 'acta' | 'qr_acta'
type FlashKind = 'loading' | 'success' | 'error' | 'info'
type FlashMessage = { kind: FlashKind; text: string; warnings?: string[] } | null

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
  apellidos: string
  nombres: string
}

type ActaName = {
  nombres?: string | null
  primer_apellido?: string | null
  segundo_apellido?: string | null
  nombre_completo?: string | null
}

type Reference = {
  nombre: string
  nombrePartes: PersonName
  domicilio: Address
  parentesco: string
}

type PhotoSet = {
  frenteCuadro: string
  frenteOvalo: string
  perfilOvalo: string
  frente?: string
  perfil?: string
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
  fotos: PhotoSet
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
  apellidos: '',
  nombres: '',
}

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

function cleanUpper(value: string) {
  return value.replace(/\s+/g, ' ').trim().toUpperCase()
}

function cleanText(value: string) {
  return value.replace(/\s+/g, ' ').trim()
}

function normalizeDeep<T>(value: T, keyName = ''): T {
  if (typeof value === 'string') {
    const cleaned = cleanText(value)
    if (cleaned.startsWith('data:image/') || keyName.toLowerCase().includes('foto')) return cleaned as T
    return (keyName.toLowerCase().includes('correo') ? cleaned : cleaned.toUpperCase()) as T
  }
  if (Array.isArray(value)) return value.map((item) => normalizeDeep(item, keyName)) as T
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, nested]) => [key, normalizeDeep(nested, key)]),
    ) as T
  }
  return value
}

function composeName(value: PersonName) {
  return [value.apellidos, value.nombres]
    .map(cleanUpper)
    .filter(Boolean)
    .join(' ')
}

function splitStoredName(value?: string | null): PersonName {
  const parts = cleanUpper(value ?? '').split(' ').filter(Boolean)
  if (parts.length >= 3) {
    return {
      apellidos: parts.slice(0, 2).join(' '),
      nombres: parts.slice(2).join(' '),
    }
  }
  return { ...emptyName, nombres: cleanUpper(value ?? '') }
}

function splitNaturalName(value?: string | null): PersonName {
  const parts = cleanUpper(value ?? '').split(' ').filter(Boolean)
  if (parts.length >= 3) {
    return {
      apellidos: parts.slice(-2).join(' '),
      nombres: parts.slice(0, -2).join(' '),
    }
  }
  return { ...emptyName, nombres: cleanUpper(value ?? '') }
}

function splitActaName(value?: ActaName | null): PersonName {
  const apellidos = [value?.primer_apellido, value?.segundo_apellido]
    .map((part) => cleanUpper(part ?? ''))
    .filter(Boolean)
    .join(' ')
  const nombres = cleanUpper(value?.nombres ?? '')
  if (apellidos || nombres) return { apellidos, nombres }
  return splitNaturalName(value?.nombre_completo)
}

function mergeName(parts?: Partial<PersonName>, fullName?: string | null): PersonName {
  const fallback = splitStoredName(fullName)
  const legacyParts = parts as Partial<PersonName> & { apellidoPaterno?: string; apellidoMaterno?: string }
  const legacyApellidos = [legacyParts?.apellidoPaterno, legacyParts?.apellidoMaterno].map((value) => value ?? '').join(' ').trim()
  return {
    apellidos: parts?.apellidos ?? (legacyApellidos || fallback.apellidos),
    nombres: parts?.nombres ?? fallback.nombres,
  }
}

function referenceLabel(references: Reference[], index: number) {
  const current = references[index]
  const number = references
    .slice(0, index + 1)
    .filter((reference) => reference.parentesco === current.parentesco).length
  return `${current.parentesco} ${number}`
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
  fotos: {
    frenteCuadro: '',
    frenteOvalo: '',
    perfilOvalo: '',
  },
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
    fotos: {
      ...emptyForm.fotos,
      ...(merged.fotos ?? {}),
      frenteCuadro: merged.fotos?.frenteCuadro || merged.fotos?.frente || '',
      frenteOvalo: merged.fotos?.frenteOvalo || merged.fotos?.frente || '',
      perfilOvalo: merged.fotos?.perfilOvalo || merged.fotos?.perfil || '',
    },
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

function extractDigits(value?: string | number | null) {
  const match = String(value ?? '').match(/\d+/)
  return match ? match[0] : ''
}

function keepValidDigits(current: string, extracted?: string | number | null) {
  return /^\d+$/.test(current) ? current : extractDigits(extracted)
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
  const currentNoActa = keepValidDigits(current.noActa, registro.numero_acta)
  const currentLibro = keepValidDigits(current.libro, registro.libro)
  const extractedName = persona.nombre_completo || ''
  const nombrePartes = current.nombreCompleto ? current.nombrePartes : splitActaName(persona)
  const padreNombrePartes = current.padre ? current.padreNombrePartes : splitActaName(filiacion[0])
  const madreNombrePartes = current.madre ? current.madreNombrePartes : splitActaName(filiacion[1])
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
    noActa: currentNoActa,
    anioActa: currentYear || extractedYear,
    libro: currentLibro,
    lugar: current.lugar || 'TOLUCA, MEXICO',
    fechaFiliacion: current.fechaFiliacion || todayIso(),
  }
}

function documentActionLabel(tipo: DocType, busy: boolean) {
  if (busy) return tipo === 'qr_acta' ? 'Analizando QR...' : 'Analizando...'
  return tipo === 'qr_acta' ? 'Analizar QR' : 'Analizar documento'
}

const applicantSections = [
  { id: 'datos-solicitante', label: 'Datos personales' },
  { id: 'domicilio-solicitante', label: 'Domicilio particular' },
  { id: 'referencias-solicitante', label: 'Referencias' },
]

const reviewSections = [
  { id: 'documentos', label: 'Documentos' },
  { id: 'administrativos', label: 'Datos administrativos' },
  { id: 'identidad', label: 'Identidad y registro' },
  { id: 'contacto', label: 'Estado civil y contacto' },
  { id: 'domicilio-revision', label: 'Domicilio' },
  { id: 'referencias-revision', label: 'Referencias' },
  { id: 'fotografias', label: 'Fotografías' },
  { id: 'rasgos', label: 'Rasgos físicos' },
  { id: 'notas', label: 'Notas de revisión' },
]

function SectionNav({ items, review = false }: { items: typeof applicantSections; review?: boolean }) {
  const [active, setActive] = useState(items[0].id)

  useEffect(() => {
    let frame = 0
    function updateActiveSection() {
      frame = 0
      const threshold = (document.querySelector('.topbar')?.getBoundingClientRect().bottom ?? 80) + 32
      let current = items[0].id
      for (const { id } of items) {
        const element = document.getElementById(id)
        if (element && element.getBoundingClientRect().top <= threshold) current = id
      }
      if (window.scrollY > 0 && window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) {
        current = items[items.length - 1].id
      }
      setActive(current)
    }
    function scheduleUpdate() {
      if (!frame) frame = window.requestAnimationFrame(updateActiveSection)
    }
    updateActiveSection()
    window.addEventListener('scroll', scheduleUpdate, { passive: true })
    window.addEventListener('resize', scheduleUpdate)
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('scroll', scheduleUpdate)
      window.removeEventListener('resize', scheduleUpdate)
    }
  }, [items])

  return (
    <aside className="section-sidebar">
      <nav className="section-nav" aria-label={review ? 'Secciones de revisión' : 'Secciones de la solicitud'}>
        <p className="nav-caption">{review ? 'En este expediente' : 'Tu solicitud'}</p>
        {items.map(({ id, label }, index) => (
          <a key={id} href={`#${id}`} aria-current={active === id ? 'location' : undefined} onClick={() => setActive(id)}>
            <span className="nav-number">{String(index + 1).padStart(2, '0')}</span>
            <span>{label}</span>
            <ChevronRight size={14} aria-hidden="true" />
          </a>
        ))}
        <div className="sidebar-note">
          <FileSearch size={20} aria-hidden="true" />
          <strong>{review ? 'Revisión del expediente' : 'Antes de enviar'}</strong>
          <p>{review ? 'Contrasta la información capturada con los documentos y guarda los cambios al finalizar.' : 'Ten a la mano tus datos personales y los domicilios de tus cuatro referencias.'}</p>
        </div>
      </nav>
    </aside>
  )
}

function SectionHeading({ number, title, description }: { number: string; title: string; description?: string }) {
  return (
    <div className="section-heading">
      <span className="section-number" aria-hidden="true">{number}</span>
      <div><h2>{title}</h2>{description && <p>{description}</p>}</div>
    </div>
  )
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

function solicitudName(solicitud: Solicitud) {
  return solicitud.nombre_completo || solicitud.datos?.nombreCompleto || 'Sin nombre'
}

function solicitudEmail(solicitud: Solicitud) {
  return solicitud.correo_electronico || solicitud.datos?.correoElectronico || 'Sin correo'
}

function statusClassName(status: string) {
  const normalized = cleanUpper(status)
  if (normalized.includes('REVIS')) return 'revisada'
  if (normalized.includes('RECHAZ')) return 'rechazada'
  return 'pendiente'
}

function getRevisionSolicitudId(pathname: string) {
  const match = pathname.replace(/\/$/, '').match(/^\/revision\/([^/]+)$/)
  return match?.[1] ?? null
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
  const currentOption = value.colonia
    ? {
        asentamiento: value.colonia,
        municipio: value.municipio,
        estado: value.estado,
      }
    : null
  const hasCurrentInOptions = options.some(
    (option) =>
      sameText(option.asentamiento, value.colonia) &&
      sameText(option.municipio, value.municipio) &&
      sameText(option.estado, value.estado),
  )
  const displayedOptions = currentOption && !hasCurrentInOptions ? [currentOption, ...options] : options
  const selectedOptionIndex = displayedOptions.findIndex(
    (option) =>
      sameText(option.asentamiento, value.colonia) &&
      sameText(option.municipio, value.municipio) &&
      sameText(option.estado, value.estado),
  )

  function update(field: keyof Address, next: string) {
    const normalized = field === 'cp' ? next : next.toUpperCase()
    const nextValue = { ...value, [field]: normalized }
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
      colonia: option.asentamiento.toUpperCase(),
      municipio: option.municipio.toUpperCase(),
      estado: option.estado.toUpperCase(),
    })
  }

  return (
    <fieldset className="address-block">
      <legend>{label}</legend>
      <div className="cp-search">
        <label>Código postal<input value={value.cp} inputMode="numeric" autoComplete="postal-code" maxLength={5} onChange={(event) => update('cp', event.target.value.replace(/\D/g, ''))} onKeyDown={(event) => {
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
      <label className="colony-select">Colonia o delegación
        <select
          value={selectedOptionIndex >= 0 ? String(selectedOptionIndex) : ''}
          disabled={displayedOptions.length === 0}
          onChange={(event) => applyOption(displayedOptions[Number(event.target.value)])}
        >
          <option value="">{displayedOptions.length ? 'Selecciona colonia' : 'Consulta primero el CP'}</option>
          {displayedOptions.map((option, index) => (
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

function sameText(left?: string | null, right?: string | null) {
  return cleanUpper(left ?? '') === cleanUpper(right ?? '')
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
      <label>Apellidos<input disabled={disabled} value={value.apellidos} onChange={(event) => update('apellidos', event.target.value)} /></label>
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
          <option value="Union libre">Unión libre</option>
        </select>
      </label>
      <div className={`spouse-name-wrapper ${!spouseEnabled ? 'disabled-name-block' : ''}`}>
        <NameFields
          label="Nombre del cónyuge"
          value={spouseEnabled ? conyugePartes : mergeName(undefined, conyuge)}
          onChange={onConyuge}
          disabled={!spouseEnabled}
        />
      </div>
    </>
  )
}

function StatusModal({ message, onClose }: { message: NonNullable<FlashMessage>; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const isLoading = message.kind === 'loading'
  useEffect(() => {
    const dialog = dialogRef.current
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog?.showModal()
    return () => {
      dialog?.close()
      document.body.style.overflow = previousOverflow
    }
  }, [])

  useEffect(() => {
    if (!isLoading) dialogRef.current?.querySelector('button')?.focus()
  }, [isLoading])
  const title =
    message.kind === 'loading'
      ? 'Procesando'
      : message.kind === 'success'
        ? 'Listo'
        : message.kind === 'error'
          ? 'No se pudo completar'
          : 'Aviso'

  return (
    <dialog ref={dialogRef} className="status-dialog" aria-labelledby="status-title" aria-describedby="status-description" onCancel={(event) => {
      event.preventDefault()
      if (!isLoading) onClose()
    }}>
      <div className={`status-modal ${message.kind}`}>
        {isLoading ? <span className="modal-spinner" aria-hidden="true" /> : message.kind === 'error' ? <AlertCircle size={34} aria-hidden="true" /> : message.kind === 'info' ? <Info size={34} aria-hidden="true" /> : <span className="modal-check" aria-hidden="true">✓</span>}
        <h2 id="status-title">{title}</h2>
        <p id="status-description" role="status">{message.text}</p>
        {message.warnings && message.warnings.length > 0 && (
          <div className="modal-warnings">
            <strong>Advertencias detectadas</strong>
            <ul>
              {message.warnings.map((warning, index) => (
                <li key={index}>{warning}</li>
              ))}
            </ul>
          </div>
        )}
        {!isLoading && (
          <button className="primary" type="button" onClick={onClose}>
            Aceptar
          </button>
        )}
      </div>
    </dialog>
  )
}

function PhotoCapture({
  label,
  aspect,
  shape,
  value,
  onChange,
}: {
  label: string
  aspect: number
  shape: 'square' | 'oval'
  value: string
  onChange: (value: string) => void
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [active, setActive] = useState(false)
  const [error, setError] = useState('')
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [deviceId, setDeviceId] = useState('')
  const [compatMode, setCompatMode] = useState(false)
  const statusLabel = active ? 'Activa' : value ? 'Capturada' : 'Pendiente'
  const statusClass = active ? 'active' : value ? 'done' : 'pending'

  useEffect(() => {
    if (!active || !streamRef.current || !videoRef.current) return
    videoRef.current.srcObject = streamRef.current
    videoRef.current.play().catch(() => setError('La camara se abrio, pero el navegador no pudo iniciar la vista previa.'))
  }, [active])

  useEffect(() => {
    async function loadInitialDevices() {
      if (!navigator.mediaDevices?.enumerateDevices) return
      const found = await navigator.mediaDevices.enumerateDevices()
      const cameras = found.filter((device) => device.kind === 'videoinput')
      setDevices(cameras)
      const obsCam = cameras.find((device) => device.label.toLowerCase().includes('obs'))
      const droidCam = cameras.find((device) => device.label.toLowerCase().includes('droid'))
      setDeviceId((obsCam ?? droidCam ?? cameras[0])?.deviceId ?? '')
    }

    loadInitialDevices()
    return () => stopCamera()
  }, [])

  async function loadDevices() {
    if (!navigator.mediaDevices?.enumerateDevices) return
    const found = await navigator.mediaDevices.enumerateDevices()
    const cameras = found.filter((device) => device.kind === 'videoinput')
    setDevices(cameras)
    if (!deviceId) {
      const obsCam = cameras.find((device) => device.label.toLowerCase().includes('obs'))
      const droidCam = cameras.find((device) => device.label.toLowerCase().includes('droid'))
      setDeviceId((obsCam ?? droidCam ?? cameras[0])?.deviceId ?? '')
    }
  }

  async function startCamera() {
    setError('')
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('La camara no esta disponible en este navegador.')
      return
    }
    try {
      const size = compatMode
        ? { width: { ideal: 640 }, height: { ideal: 480 } }
        : { width: { ideal: 1280 }, height: { ideal: 720 } }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: 'user' }),
          ...size,
        },
        audio: false,
      })
      streamRef.current = stream
      setActive(true)
      await loadDevices()
    } catch {
      setError('No se pudo abrir la camara. Si usas DroidCam, confirma que este activo y seleccionado.')
    }
  }

  function stopCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setActive(false)
  }

  function capture() {
    const video = videoRef.current
    if (!video || !video.videoWidth || !video.videoHeight) return
    const canvas = document.createElement('canvas')
    canvas.width = 640
    canvas.height = Math.round(canvas.width / aspect)
    const context = canvas.getContext('2d')
    if (!context) return
    const sourceAspect = video.videoWidth / video.videoHeight
    let sx = 0
    let sy = 0
    let sw = video.videoWidth
    let sh = video.videoHeight
    if (sourceAspect > aspect) {
      sw = Math.round(video.videoHeight * aspect)
      sx = Math.round((video.videoWidth - sw) / 2)
    } else {
      sh = Math.round(video.videoWidth / aspect)
      sy = Math.round((video.videoHeight - sh) / 2)
    }
    const trimmed = trimDarkFrame(video, sx, sy, sw, sh)
    sx = trimmed.sx
    sy = trimmed.sy
    sw = trimmed.sw
    sh = trimmed.sh
    // Capture the inside of the on-screen guide instead of keeping the camera margins.
    const guideInset = 0
    sx += Math.round(sw * guideInset)
    sy += Math.round(sh * guideInset)
    sw = Math.max(1, Math.round(sw * (1 - guideInset * 2)))
    sh = Math.max(1, Math.round(sh * (1 - guideInset * 2)))
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, canvas.width, canvas.height)

    const sourceRatio = sw / sh
    const canvasRatio = canvas.width / canvas.height
    let drawWidth = canvas.width
    let drawHeight = canvas.height
    let dx = 0
    let dy = 0
    if (sourceRatio > canvasRatio) {
      drawHeight = Math.round(canvas.width / sourceRatio)
      dy = Math.round((canvas.height - drawHeight) / 2)
    } else {
      drawWidth = Math.round(canvas.height * sourceRatio)
      dx = Math.round((canvas.width - drawWidth) / 2)
    }

    context.drawImage(video, sx, sy, sw, sh, dx, dy, drawWidth, drawHeight)
    onChange(canvas.toDataURL('image/jpeg', 0.9))
    stopCamera()
  }

  function trimDarkFrame(video: HTMLVideoElement, sx: number, sy: number, sw: number, sh: number) {
    const sample = document.createElement('canvas')
    const sampleWidth = 180
    const sampleHeight = Math.max(1, Math.round(sampleWidth * (sh / sw)))
    sample.width = sampleWidth
    sample.height = sampleHeight
    const context = sample.getContext('2d', { willReadFrequently: true })
    if (!context) return { sx, sy, sw, sh }
    context.drawImage(video, sx, sy, sw, sh, 0, 0, sampleWidth, sampleHeight)
    const pixels = context.getImageData(0, 0, sampleWidth, sampleHeight).data
    const isVisible = (index: number) => pixels[index] + pixels[index + 1] + pixels[index + 2] > 45
    let left = 0
    let right = sampleWidth - 1
    let top = 0
    let bottom = sampleHeight - 1

    for (; left < sampleWidth; left += 1) {
      let count = 0
      for (let y = 0; y < sampleHeight; y += 1) if (isVisible((y * sampleWidth + left) * 4)) count += 1
      if (count > sampleHeight * 0.18) break
    }
    for (; right > left; right -= 1) {
      let count = 0
      for (let y = 0; y < sampleHeight; y += 1) if (isVisible((y * sampleWidth + right) * 4)) count += 1
      if (count > sampleHeight * 0.18) break
    }
    for (; top < sampleHeight; top += 1) {
      let count = 0
      for (let x = 0; x < sampleWidth; x += 1) if (isVisible((top * sampleWidth + x) * 4)) count += 1
      if (count > sampleWidth * 0.18) break
    }
    for (; bottom > top; bottom -= 1) {
      let count = 0
      for (let x = 0; x < sampleWidth; x += 1) if (isVisible((bottom * sampleWidth + x) * 4)) count += 1
      if (count > sampleWidth * 0.18) break
    }

    const trimWidth = right - left + 1
    const trimHeight = bottom - top + 1
    if (trimWidth < sampleWidth * 0.45 || trimHeight < sampleHeight * 0.45) return { sx, sy, sw, sh }
    return {
      sx: sx + Math.round((left / sampleWidth) * sw),
      sy: sy + Math.round((top / sampleHeight) * sh),
      sw: Math.round((trimWidth / sampleWidth) * sw),
      sh: Math.round((trimHeight / sampleHeight) * sh),
    }
  }

  return (
    <div className="photo-capture">
      <div className="photo-card-header">
        <div className="photo-title">
          <span className={`photo-shape-token ${shape}`} />
          <strong>{label.replace('Tomar ', '')}</strong>
        </div>
        <span className={`photo-status ${statusClass}`}>{statusLabel}</span>
      </div>
      <div className={`photo-preview ${shape}`}>
        {active ? (
          <video ref={videoRef} autoPlay playsInline muted />
        ) : value ? (
          <img src={value} alt={label} />
        ) : (
          <div className="photo-placeholder">
            <Camera size={30} />
            <span>{label}</span>
          </div>
        )}
        <span className="photo-frame-guide" />
      </div>
      {!active && (
        <div className="photo-settings">
          <label className="camera-select">Cámara
            <select value={deviceId} onChange={(event) => setDeviceId(event.target.value)}>
              {devices.length > 0 ? (
                devices.map((device, index) => (
                  <option value={device.deviceId} key={device.deviceId}>{device.label || `Cámara ${index + 1}`}</option>
                ))
              ) : (
                <option value="">Sin cámaras detectadas</option>
              )}
            </select>
          </label>
          <div className="camera-controls">
            <button className="secondary icon-button" type="button" onClick={loadDevices} aria-label="Actualizar cámaras" title="Actualizar cámaras">
              <RefreshCw size={16} />
            </button>
            <label className="compat-toggle">
              <input type="checkbox" checked={compatMode} onChange={(event) => setCompatMode(event.target.checked)} />
              Compatibilidad
            </label>
          </div>
        </div>
      )}
      <div className="photo-actions">
        {!active ? (
          <button className="secondary" type="button" onClick={startCamera}>
            <Camera size={17} /> {value ? 'Retomar foto' : label}
          </button>
        ) : (
          <>
            <button className="primary" type="button" onClick={capture}>
              <Camera size={17} /> Capturar
            </button>
            <button className="secondary" type="button" onClick={stopCamera}>
              <RotateCcw size={17} /> Cancelar
            </button>
          </>
        )}
        {value && !active && (
          <button className="secondary danger" type="button" onClick={() => onChange('')}>
            <Trash2 size={17} /> Quitar
          </button>
        )}
      </div>
      {error && <p className="field-error">{error}</p>}
    </div>
  )
}

function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname.replace(/\/$/, '') || '/')
  const view: View = pathname === '/revision' || pathname.startsWith('/revision/') ? 'revision' : 'solicitante'
  const revisionSolicitudId = view === 'revision' ? getRevisionSolicitudId(pathname) : null
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
  const [flash, setFlash] = useState<FlashMessage>(null)
  const [busyAction, setBusyAction] = useState('')

  const warnings = useMemo(() => {
    const value = lastExtraction?.resultado?.advertencias
    return Array.isArray(value) ? value : []
  }, [lastExtraction])

  const solicitudStats = useMemo(() => {
    return solicitudes.reduce(
      (stats, solicitud) => {
        const status = statusClassName(solicitud.estado)
        return {
          total: stats.total + 1,
          pendientes: stats.pendientes + (status === 'pendiente' ? 1 : 0),
          revisadas: stats.revisadas + (status === 'revisada' ? 1 : 0),
        }
      },
      { total: 0, pendientes: 0, revisadas: 0 },
    )
  }, [solicitudes])

  useEffect(() => {
    function handlePopState() {
      setPathname(window.location.pathname.replace(/\/$/, '') || '/')
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (view !== 'revision' || !token) return

    let active = true

    async function loadInitialSolicitudes() {
      const response = await fetch('/api/solicitudes', { headers: authHeaders(token) })
      const payload = await readApiResponse(response)
      if (!active) return
      if (!response.ok) {
        setFlash({ kind: 'error', text: payload.detail ?? 'No se pudieron cargar solicitudes.' })
        return
      }
      setSolicitudes(payload)
      if (revisionSolicitudId) {
        const solicitud = payload.find((item: Solicitud) => item.id === revisionSolicitudId)
        if (solicitud) {
          setSelected(solicitud)
          setOperatorForm(mergeForm(solicitud.datos))
          setOperatorNotes(solicitud.notas_operador ?? '')
          setLastExtraction(null)
          setFile(null)
        } else {
          setSelected(null)
          setFlash({ kind: 'error', text: 'No se encontro la solicitud solicitada.' })
        }
      }
    }

    loadInitialSolicitudes()
    return () => {
      active = false
    }
  }, [view, token, revisionSolicitudId])

  function showMessage(kind: FlashKind, text: string, warnings?: string[]) {
    setFlash({ kind, text, warnings })
  }

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
    setBusyAction('submit')
    showMessage('loading', 'Enviando solicitud...')
    const cleanForm = normalizeDeep(requestForm)
    const response = await fetch('/api/solicitudes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        estado: 'enviada',
        curp: cleanForm.curp || null,
        nombre_completo: cleanForm.nombreCompleto || null,
        correo_electronico: cleanForm.correoElectronico || null,
        datos: cleanForm,
        extracciones: [],
      }),
    })
    const payload = await readApiResponse(response)
    setBusyAction('')
    if (!response.ok) {
      showMessage('error', payload.detail ?? 'No se pudo enviar la solicitud.')
      return
    }
    setRequestForm(mergeForm())
    showMessage('success', `Solicitud enviada. Folio técnico: ${payload.id}`)
  }

  async function loginOperator(event: FormEvent) {
    event.preventDefault()
    setBusyAction('login')
    showMessage('loading', 'Validando acceso...')
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(login),
    })
    const payload = await readApiResponse(response)
    setBusyAction('')
    if (!response.ok) {
      showMessage('error', payload.detail ?? 'No se pudo iniciar sesión.')
      return
    }
    localStorage.setItem('revisionToken', payload.token)
    localStorage.setItem('revisionUser', payload.username)
    setToken(payload.token)
    setUsername(payload.username)
    showMessage('success', `Sesión iniciada como ${payload.username}`)
  }

  async function loadSolicitudes() {
    if (!token) return
    const response = await fetch('/api/solicitudes', { headers: authHeaders(token) })
    const payload = await readApiResponse(response)
    if (!response.ok) {
      showMessage('error', payload.detail ?? 'No se pudieron cargar solicitudes.')
      return
    }
    setSolicitudes(payload)
    if (revisionSolicitudId) {
      const solicitud = payload.find((item: Solicitud) => item.id === revisionSolicitudId)
      if (solicitud) {
        selectSolicitud(solicitud)
      } else {
        setSelected(null)
        showMessage('error', 'No se encontro la solicitud solicitada.')
      }
    }
  }

  function selectSolicitud(solicitud: Solicitud) {
    setSelected(solicitud)
    setOperatorForm(mergeForm(solicitud.datos))
    setOperatorNotes(solicitud.notas_operador ?? '')
    setLastExtraction(null)
    setFile(null)
  }

  function navigateToRevision(solicitud: Solicitud) {
    selectSolicitud(solicitud)
    const nextPath = `/revision/${solicitud.id}`
    window.history.pushState({}, '', nextPath)
    setPathname(nextPath)
  }

  function backToSolicitudes() {
    window.history.pushState({}, '', '/revision')
    setPathname('/revision')
    setSelected(null)
    setLastExtraction(null)
    setFile(null)
  }

  async function handleExtraction(event: FormEvent) {
    event.preventDefault()
    if (!file) {
      showMessage('error', 'Selecciona una imagen o PDF.')
      return
    }

    setBusyAction('extract')
    showMessage('loading', tipo === 'qr_acta' ? 'Leyendo QR y consultando enlace...' : 'Analizando documento...')

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
    setBusyAction('')
    if (!response.ok) {
      showMessage('error', payload.detail ?? 'No se pudo analizar el documento.')
      return
    }
    setLastExtraction(payload)
    setOperatorForm((current) => applyExtraction(current, tipo, payload))
    const extractionWarnings = Array.isArray(payload?.resultado?.advertencias) ? payload.resultado.advertencias : []
    showMessage(
      'success',
      extractionWarnings.length
        ? 'Extracción aplicada al formulario de revisión. Revisa las advertencias antes de guardar.'
        : 'Extracción aplicada al formulario de revisión.',
      extractionWarnings,
    )
  }

  async function saveReview() {
    if (!selected) return
    setBusyAction('save')
    showMessage('loading', 'Guardando revisión...')
    const cleanForm = normalizeDeep(operatorForm)
    const extracciones = lastExtraction ? [...(selected.extracciones ?? []), lastExtraction] : selected.extracciones ?? []
    const response = await fetch(`/api/solicitudes/${selected.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
      body: JSON.stringify({
        estado: 'revisada',
        curp: cleanForm.curp || null,
        nombre_completo: cleanForm.nombreCompleto || null,
        correo_electronico: cleanForm.correoElectronico || null,
        datos: cleanForm,
        extracciones,
        notas_operador: cleanText(operatorNotes).toUpperCase(),
      }),
    })
    const payload = await readApiResponse(response)
    setBusyAction('')
    if (!response.ok) {
      showMessage('error', payload.detail ?? 'No se pudo guardar la revisión.')
      return
    }
    showMessage('success', `Revisión guardada por ${payload.revisado_por}`)
    setSelected(payload)
    setSolicitudes((items) => items.map((item) => (item.id === payload.id ? payload : item)))
  }

  async function downloadExcel() {
    if (!selected) return
    setBusyAction('excel')
    showMessage('loading', 'Generando Excel...')
    const cleanForm = normalizeDeep(operatorForm)
    const response = await fetch(`/api/solicitudes/${selected.id}/excel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
      body: JSON.stringify({
        datos: cleanForm,
      }),
    })
    if (!response.ok) {
      const payload = await readApiResponse(response)
      setBusyAction('')
      showMessage('error', payload.detail ?? 'No se pudo generar el Excel.')
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
    setBusyAction('')
    showMessage('success', 'Excel descargado.')
  }

  return (
    <main className="app-shell">
      <a className="skip-link" href="#contenido">Ir al contenido</a>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="/" aria-label="SEIEM, inicio de solicitud">
            <span className="brand-wordmark">SEIEM<span aria-hidden="true">.</span></span>
            <span className="brand-description">Servicios Educativos Integrados<br />al Estado de México</span>
          </a>
          <div className="topbar-context">
            <span className="platform-label">Plataforma de filiación</span>
            {view === 'revision' && token
              ? <span className="operator-badge"><Lock size={14} aria-hidden="true" /> {username}</span>
              : <span className="topbar-label">{view === 'revision' ? 'Acceso de personal' : 'Registro de solicitantes'}</span>}
          </div>
        </div>
      </header>
      <section className={`workspace ${view}-workspace`}>
        <header className="page-header" id="contenido" tabIndex={-1}>
          <div>
            <p className="eyebrow">Filiación <ChevronRight size={13} aria-hidden="true" /> {view === 'solicitante' ? 'Nueva solicitud' : 'Gestión de solicitudes'}</p>
            <h1>
              {view === 'solicitante'
                ? 'Solicitud de filiación'
                : revisionSolicitudId
                  ? 'Revisión del expediente'
                  : 'Revisión de solicitudes'}
            </h1>
            <p className="page-description">{view === 'solicitante'
              ? 'Completa tus datos y referencias para iniciar tu trámite de filiación.'
              : !token ? 'Ingresa con tu cuenta de personal para revisar y gestionar los expedientes.'
              : revisionSolicitudId ? 'Verifica los documentos y completa la información del solicitante.'
              : 'Consulta los registros recibidos y da seguimiento a cada expediente.'}</p>
          </div>
          <span className="page-tag"><span aria-hidden="true" />{view === 'solicitante' ? 'Captura de información' : 'Área de revisión'}</span>
        </header>

        {flash && <StatusModal message={flash} onClose={() => setFlash(null)} />}

        {view === 'solicitante' ? (
          <SolicitanteForm
            form={requestForm}
            setField={setRequestField}
            setAddress={(domicilio) => setRequestField('domicilio', domicilio)}
            updateReference={updateReference}
            saving={busyAction === 'submit'}
            onSubmit={submitSolicitud}
          />
        ) : !token ? (
          <div className="login-layout">
          <div className="login-intro">
            <Lock size={28} aria-hidden="true" />
            <h2>Gestión de filiación</h2>
            <p>Un espacio para consultar solicitudes, verificar documentos y completar los registros de filiación.</p>
            <span>Uso exclusivo del personal autorizado</span>
          </div>
          <form className="login-panel" onSubmit={loginOperator}>
            <div><p className="eyebrow">Acceso de personal</p><h2>Iniciar sesión</h2></div>
            <label>Usuario<input autoComplete="username" required value={login.username} onChange={(event) => setLogin({ ...login, username: event.target.value })} /></label>
            <label>Contraseña<input type="password" autoComplete="current-password" required value={login.password} onChange={(event) => setLogin({ ...login, password: event.target.value })} /></label>
            <button className="primary" type="submit" disabled={busyAction === 'login'}>
              {busyAction === 'login' ? 'Validando...' : 'Ingresar al panel'}<ArrowUpRight size={17} aria-hidden="true" />
            </button>
          </form>
          </div>
        ) : (
          <section className={`operator-grid ${revisionSolicitudId ? 'detail-mode' : 'list-mode'}`}>
            {!revisionSolicitudId && (
            <div className="requests-list">
              <div className="requests-header">
                <div>
                  <div className="section-title"><ListChecks size={20} /><h2>Solicitudes</h2></div>
                  <span>{solicitudes.length} registro{solicitudes.length === 1 ? '' : 's'} disponibles</span>
                </div>
                <button className="secondary" type="button" onClick={loadSolicitudes}>
                  <RefreshCw size={17} /> Actualizar
                </button>
              </div>
              <div className="requests-kpis" aria-label="Resumen de solicitudes">
                <div>
                  <span>Total</span>
                  <strong>{solicitudStats.total}</strong>
                </div>
                <div>
                  <span>Pendientes</span>
                  <strong>{solicitudStats.pendientes}</strong>
                </div>
                <div>
                  <span>Revisadas</span>
                  <strong>{solicitudStats.revisadas}</strong>
                </div>
              </div>
              <div className="requests-table-wrapper">
                <table className="requests-table">
                  <thead>
                    <tr>
                      <th>Solicitante</th>
                      <th>CURP</th>
                      <th>Contacto</th>
                      <th>Fecha</th>
                      <th>Estado</th>
                      <th>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {solicitudes.map((solicitud) => (
                      <tr className={selected?.id === solicitud.id ? 'selected' : ''} key={solicitud.id}>
                        <td data-label="Solicitante">
                          <strong>{solicitudName(solicitud)}</strong>
                          <span>ID {solicitud.id}</span>
                        </td>
                        <td data-label="CURP">{solicitud.curp || solicitud.datos?.curp || 'Pendiente'}</td>
                        <td data-label="Contacto">{solicitudEmail(solicitud)}</td>
                        <td data-label="Fecha">{new Date(solicitud.created_at).toLocaleString()}</td>
                        <td data-label="Estado">
                          <span className={`status-pill ${statusClassName(solicitud.estado)}`}>{solicitud.estado}</span>
                        </td>
                        <td data-label="Acción">
                          <button className="review-button" type="button" onClick={() => navigateToRevision(solicitud)}>
                            <FileSearch size={16} /> Revisar
                          </button>
                        </td>
                      </tr>
                    ))}
                    {solicitudes.length === 0 && (
                      <tr>
                        <td className="empty-table" colSpan={6}><ListChecks size={28} aria-hidden="true" /><strong>Aún no hay solicitudes</strong><span>Los registros recibidos aparecerán aquí para su revisión.</span></td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            )}

            {revisionSolicitudId && (
            <div className="form-layout">
            {selected && <SectionNav items={reviewSections} review />}
            <div className="review-panel">
              {selected ? (
                <>
                  <div className="review-toolbar">
                    <button className="secondary" type="button" onClick={backToSolicitudes}>
                      <ArrowLeft size={18} /> Volver a solicitudes
                    </button>
                  </div>
                  <section className="selected-summary">
                    <div>
                      <span>Solicitud seleccionada</span>
                      <strong>{selected.nombre_completo || selected.datos?.nombreCompleto || 'Sin nombre'}</strong>
                    </div>
                    <div>
                      <span>Estado</span>
                      <strong>{selected.estado}</strong>
                    </div>
                    <div>
                      <span>Fecha</span>
                      <strong>{new Date(selected.created_at).toLocaleString()}</strong>
                    </div>
                  </section>

                  <section className="document-panel" id="documentos" aria-label="Documentos">
                    <form className="upload-panel" onSubmit={handleExtraction}>
                      <SectionHeading number="01" title="Análisis de documentos" description="Selecciona el tipo de documento y carga una imagen o un PDF para obtener sus datos." />
                      <div className="segmented" role="group" aria-label="Tipo de documento">
                        <button type="button" aria-pressed={tipo === 'ine'} className={tipo === 'ine' ? 'selected' : ''} onClick={() => setTipo('ine')}>INE</button>
                        <button type="button" aria-pressed={tipo === 'acta'} className={tipo === 'acta' ? 'selected' : ''} onClick={() => setTipo('acta')}>Acta</button>
                        <button type="button" aria-pressed={tipo === 'qr_acta'} className={tipo === 'qr_acta' ? 'selected' : ''} onClick={() => setTipo('qr_acta')}><QrCode size={16} /> QR acta</button>
                      </div>
                      <label className="file-drop">
                        <Upload size={22} />
                        <span>{file ? file.name : 'Seleccionar imagen o PDF'}</span>
                        <input type="file" accept=".jpg,.jpeg,.png,.bmp,.tif,.tiff,.webp,.pdf" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} />
                      </label>
                      {tipo === 'ine' && <label className="inline-label">Página PDF<input type="number" min="1" value={pagina} onChange={(event) => setPagina(Number(event.target.value))} /></label>}
                      <button className="secondary" type="submit" disabled={!file || busyAction === 'extract'}>
                        {tipo === 'qr_acta' ? <QrCode size={18} /> : <FileSearch size={18} />}{documentActionLabel(tipo, busyAction === 'extract')}
                      </button>
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
                    saving={busyAction === 'save'}
                    downloading={busyAction === 'excel'}
                  />
                </>
              ) : (
                <p className="notice">Cargando solicitud...</p>
              )}
            </div>
            </div>
            )}
          </section>
        )}
        <footer className="site-footer"><span>SEIEM <span aria-hidden="true">/</span> Plataforma de filiación</span><span>Servicios Educativos Integrados al Estado de México</span></footer>
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
    <div className="form-layout">
    <SectionNav items={applicantSections} />
    <section className="form-flow applicant-flow">
      <section className="form-section" id="datos-solicitante">
        <SectionHeading number="01" title="Datos del solicitante" description="Escribe tu nombre y datos de contacto como aparecen en tus documentos." />
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
          <label>Teléfono<input type="tel" inputMode="tel" value={form.telefono} onChange={(event) => setField('telefono', event.target.value.replace(/\D/g, ''))} /></label>
          <label>Correo electrónico<input type="email" value={form.correoElectronico} onChange={(event) => setField('correoElectronico', event.target.value)} /></label>
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

      <section className="form-section" id="domicilio-solicitante">
        <SectionHeading number="02" title="Domicilio particular" description="Consulta tu código postal para seleccionar la colonia correspondiente." />
        <AddressFields label="Dirección" value={form.domicilio} onChange={setAddress} />
      </section>

      <section className="references" id="referencias-solicitante">
        <SectionHeading number="03" title="Referencias" description="Registra dos conocidos y dos familiares, con su nombre y domicilio." />
        <div className="reference-grid">
          {form.referencias.map((reference, index) => (
            <div className="reference-item" key={index}>
              <h3>{referenceLabel(form.referencias, index)}</h3>
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
        <p className="action-note"><Check size={16} aria-hidden="true" />Revisa la información antes de enviar tu solicitud.</p>
        <button className="primary" type="button" onClick={onSubmit} disabled={saving}><Save size={18} />{saving ? 'Enviando...' : 'Enviar solicitud'}</button>
      </div>
    </section>
    </div>
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
  downloading,
}: {
  form: CaptureForm
  setField: <K extends keyof CaptureForm>(field: K, value: CaptureForm[K]) => void
  updateReference: (index: number, field: 'nombre' | 'nombrePartes' | 'domicilio', value: string | PersonName | Address) => void
  notes: string
  setNotes: (value: string) => void
  onSave: () => void
  onDownloadExcel: () => void
  saving: boolean
  downloading: boolean
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
      <section className="form-section" id="administrativos">
        <SectionHeading number="02" title="Datos administrativos" />
        <div className="form-grid four">
          <label>Filiación / RFC<input value={form.rfc} onChange={(event) => setField('rfc', event.target.value.toUpperCase())} /></label>
          <label>CURP<input value={form.curp} onChange={(event) => setField('curp', event.target.value.toUpperCase())} /></label>
          <label>Clave de cobro<input value={form.claveCobro} onChange={(event) => setField('claveCobro', event.target.value.toUpperCase())} /></label>
          <label>Descripción de la clave<input value={form.descripcionClave} onChange={(event) => setField('descripcionClave', event.target.value.toUpperCase())} /></label>
          <label>Lugar<input value={form.lugar} onChange={(event) => setField('lugar', event.target.value.toUpperCase())} /></label>
          <label>Fecha<input type="date" value={form.fechaFiliacion} onChange={(event) => setField('fechaFiliacion', event.target.value)} /></label>
        </div>
      </section>

      <section className="form-section" id="identidad">
        <SectionHeading number="03" title="Identidad y registro civil" />
        <NameFields
          label="Nombre"
          value={form.nombrePartes}
          onChange={(parts, fullName) => {
            setField('nombrePartes', parts)
            setField('nombreCompleto', fullName)
          }}
        />
        <div className="form-grid four">
          <label>Fecha de nacimiento<input type="date" value={form.fechaNacimiento} onChange={(event) => setField('fechaNacimiento', event.target.value)} /></label>
          <label>Lugar de nacimiento<input value={form.lugarNacimiento} onChange={(event) => setField('lugarNacimiento', event.target.value.toUpperCase())} /></label>
          <label>Sexo<input value={form.sexo} onChange={(event) => setField('sexo', event.target.value.toUpperCase())} /></label>
          <label>No. acta<input value={form.noActa} onChange={(event) => setField('noActa', event.target.value.toUpperCase())} /></label>
          <label>Año<input value={form.anioActa} maxLength={4} onChange={(event) => setField('anioActa', event.target.value.replace(/\D/g, '').slice(0, 4))} /></label>
          <label>Libro<input value={form.libro} onChange={(event) => setField('libro', event.target.value.toUpperCase())} /></label>
          <label>Clase<input value={form.clase} onChange={(event) => setField('clase', event.target.value.toUpperCase())} /></label>
          <label>Cartilla S.M.N.<input value={form.cartillaSmn} onChange={(event) => setField('cartillaSmn', event.target.value.toUpperCase())} /></label>
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

      <section className="form-section" id="contacto">
        <SectionHeading number="04" title="Estado civil y contacto" />
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
          <label>Correo electrónico<input type="email" value={form.correoElectronico} onChange={(event) => setField('correoElectronico', event.target.value)} /></label>
          <label>Teléfono<input type="tel" inputMode="tel" value={form.telefono} onChange={(event) => setField('telefono', event.target.value.replace(/\D/g, ''))} /></label>
        </div>
      </section>

      <section className="form-section" id="domicilio-revision">
        <SectionHeading number="05" title="Domicilio particular" />
        <AddressFields label="Dirección" value={form.domicilio} onChange={(domicilio) => setField('domicilio', domicilio)} />
      </section>

      <section className="references" id="referencias-revision">
        <SectionHeading number="06" title="Referencias" />
        <div className="reference-grid">
          {form.referencias.map((reference, index) => (
            <div className="reference-item" key={index}>
              <h3>{referenceLabel(form.referencias, index)}</h3>
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

      <section className="form-section photo-section" id="fotografias">
        <SectionHeading number="07" title="Fotografías" description="Centra el rostro dentro de la guía y captura cada fotografía con iluminación uniforme." />
        <div className="photo-grid">
          <PhotoCapture
            label="Frente · formato cuadrado"
            aspect={1}
            shape="square"
            value={form.fotos.frenteCuadro}
            onChange={(value) => setField('fotos', { ...form.fotos, frenteCuadro: value })}
          />
          <PhotoCapture
            label="Frente · formato ovalado"
            aspect={0.72}
            shape="oval"
            value={form.fotos.frenteOvalo}
            onChange={(value) => setField('fotos', { ...form.fotos, frenteOvalo: value })}
          />
          <PhotoCapture
            label="Perfil · formato ovalado"
            aspect={0.72}
            shape="oval"
            value={form.fotos.perfilOvalo}
            onChange={(value) => setField('fotos', { ...form.fotos, perfilOvalo: value })}
          />
        </div>
      </section>

      <section className="form-section" id="rasgos">
        <SectionHeading number="08" title="Rasgos físicos" />
        <div className="form-grid four">
          {Object.entries(form.rasgos).map(([key, value]) => (
            <label key={key}>
              {{ tonoPiel: 'Tono de piel', pelo: 'Pelo', frente: 'Frente', cejas: 'Cejas', ojos: 'Ojos', nariz: 'Nariz', boca: 'Boca', estatura: 'Estatura', senasVisibles: 'Señas visibles' }[key]}
              {rasgoOptions[key as keyof CaptureForm['rasgos']].length ? (
                <select value={value} onChange={(event) => setField('rasgos', { ...form.rasgos, [key]: event.target.value })}>
                  <option value="">Selecciona</option>
                  {rasgoOptions[key as keyof CaptureForm['rasgos']].map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              ) : (
                <input value={value} onChange={(event) => setField('rasgos', { ...form.rasgos, [key]: event.target.value.toUpperCase() })} />
              )}
            </label>
          ))}
        </div>
      </section>

      <section className="form-section" id="notas">
        <SectionHeading number="09" title="Notas de revisión" />
        <label className="notes-label">Notas de revisión<textarea value={notes} onChange={(event) => setNotes(event.target.value.toUpperCase())} /></label>
      </section>

      <div className="actions-row">
        <button className="secondary" type="button" onClick={onDownloadExcel} disabled={downloading}>
          <Download size={18} />{downloading ? 'Generando...' : 'Descargar Excel'}
        </button>
        <button className="primary" type="button" onClick={onSave} disabled={saving}><Save size={18} />{saving ? 'Guardando...' : 'Guardar revisión'}</button>
      </div>
    </>
  )
}

export default App
