import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { AlertCircle, ArrowLeft, ArrowUpRight, Camera, Check, ChevronLeft, ChevronRight, Download, FileSearch, Info, ListChecks, Lock, LogOut, QrCode, RefreshCw, RotateCcw, Save, Search, Trash2, Unlock, Upload } from 'lucide-react'
import './App.css'
import { revisionBrowserSession } from './revisionSession'

type View = 'solicitante' | 'revision'
type DocType = 'ine' | 'acta' | 'qr_acta'
const enabledDocTypes: DocType[] = ['acta']
type FlashKind = 'loading' | 'success' | 'error' | 'info'
type FlashMessage = { kind: FlashKind; text: string; warnings?: string[]; title?: string } | null

type Address = {
  completo?: string
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

type Solicitud = {
  revision_token?: string | null
  bloqueo?: { usuario: string; nombre: string; propio: boolean } | null
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
  source?: 'google_sheet'
  sheet_row_number?: number
}

type SolicitudResumen = Pick<Solicitud, 'id' | 'curp' | 'nombre_completo' | 'correo_electronico' | 'created_at' | 'source' | 'sheet_row_number' | 'bloqueo'> & { datos?: Partial<CaptureForm> }

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
    nombreCompleto: merged.nombreCompleto || composeName(nombrePartes) || '',
    conyugeNombrePartes,
    nombreConyuge: merged.nombreConyuge || composeName(conyugeNombrePartes) || '',
    padreNombrePartes,
    padre: merged.padre || composeName(padreNombrePartes) || '',
    madreNombrePartes,
    madre: merged.madre || composeName(madreNombrePartes) || '',
    domicilio: completeAddress({ ...emptyAddress, ...(merged.domicilio ?? {}) }),
    referencias: emptyForm.referencias.map((item, index) => {
      const reference = { ...item, ...(merged.referencias?.[index] ?? {}) }
      const nombrePartes = mergeName(reference.nombrePartes, reference.nombre)
      return {
        ...reference,
        nombrePartes,
        nombre: reference.nombre || composeName(nombrePartes) || '',
        domicilio: completeAddress({ ...emptyAddress, ...(merged.referencias?.[index]?.domicilio ?? {}) }),
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

function keepValidDigits(current: string, extracted?: string | number | null) {
  const candidate = String(extracted ?? '')
  return /^\d+$/.test(candidate) ? candidate : /^\d+$/.test(current) ? current : ''
}

function parseIneAddress(value?: string | null, cp?: string | null): Address {
  return { ...emptyAddress, completo: value ?? '', cp: cp ?? '' }
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
      domicilio: current.domicilio.completo ? current.domicilio : parseIneAddress(datos.domicilio, datos.codigo_postal),
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
  const existingName = current.nombreCompleto || composeName(current.nombrePartes)
  const nombrePartes = existingName ? mergeName(current.nombrePartes, existingName) : splitActaName(persona)
  const padreNombrePartes = filiacion[0]?.nombre_completo ? splitActaName(filiacion[0]) : current.padreNombrePartes
  const madreNombrePartes = filiacion[1]?.nombre_completo ? splitActaName(filiacion[1]) : current.madreNombrePartes
  return {
    ...current,
    curp: datos.curp || persona.curp || current.curp || '',
    nombrePartes,
    nombreCompleto: existingName || composeName(nombrePartes) || extractedName,
    fechaNacimiento: normalizeDate(persona.fecha_nacimiento) || current.fechaNacimiento,
    lugarNacimiento: persona.lugar_nacimiento?.texto || current.lugarNacimiento || '',
    sexo: persona.sexo || current.sexo || '',
    padreNombrePartes,
    padre: filiacion[0]?.nombre_completo || current.padre || composeName(padreNombrePartes) || '',
    madreNombrePartes,
    madre: filiacion[1]?.nombre_completo || current.madre || composeName(madreNombrePartes) || '',
    noActa: currentNoActa,
    anioActa: extractedYear || currentYear,
    libro: currentLibro,
    lugar: current.lugar || 'TOLUCA, MEXICO',
    fechaFiliacion: current.fechaFiliacion || todayIso(),
  }
}

function documentActionLabel(tipo: DocType, busy: boolean) {
  if (busy) return tipo === 'qr_acta' ? 'Analizando QR...' : 'Analizando...'
  return tipo === 'qr_acta' ? 'Analizar QR' : tipo === 'acta' ? 'Analizar acta' : 'Analizar documento'
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

async function prepareImageForOcr(file: File): Promise<File> {
  if (!file.type.startsWith('image/')) return file

  const maxSide = 2200
  const bitmap = await createImageBitmap(file)
  try {
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height))
    if (scale >= 1 && file.size <= 2_500_000) return file

    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    const context = canvas.getContext('2d')
    if (!context) return file
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)

    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92))
    if (!blob || blob.size >= file.size) return file
    return new File([blob], file.name.replace(/\.[^.]+$/, '.jpg'), { type: 'image/jpeg' })
  } finally {
    bitmap.close()
  }
}

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

function solicitudName(solicitud: SolicitudResumen) {
  return solicitud.nombre_completo || solicitud.datos?.nombreCompleto || 'Sin nombre'
}

function solicitudEmail(solicitud: SolicitudResumen) {
  return solicitud.correo_electronico || solicitud.datos?.correoElectronico || 'Sin correo'
}

function getRevisionSolicitudId(pathname: string) {
  const match = pathname.replace(/\/$/, '').match(/^\/revision\/([^/]+)$/)
  return match?.[1] ?? null
}

function completeAddress(value: Address): Address {
  if (value.completo !== undefined) return value
  const parts = [value.calle, value.numeroExterior ? `No. ${value.numeroExterior}` : '',
    value.numeroInterior ? `Int. ${value.numeroInterior}` : '', value.colonia, value.municipio,
    value.estado, value.cp ? `C.P. ${value.cp}` : '']
  return { ...value, completo: parts.filter(Boolean).join(', ') }
}

function AddressFields({ value, onChange, label }: { value: Address; onChange: (value: Address) => void; label: string }) {
  return (
    <fieldset className="address-block">
      <legend>{label}</legend>
      <label className="full-address">Domicilio completo<input autoComplete="street-address" value={completeAddress(value).completo ?? ''} onChange={(event) => onChange({ ...value, completo: event.target.value.toUpperCase() })} /></label>
    </fieldset>
  )
}

function NameFields({
  label,
  value,
  fullName,
  onChange,
  disabled = false,
}: {
  label: string
  value: PersonName
  fullName?: string
  onChange: (value: PersonName, fullName: string) => void
  disabled?: boolean
}) {
  function update(next: string) {
    if (disabled) return
    const normalized = next.toUpperCase()
    onChange({ apellidos: '', nombres: normalized }, normalized)
  }

  return (
    <fieldset className="name-block">
      <legend>{label}</legend>
      <label className="full-name">Nombre completo<input disabled={disabled} value={fullName ?? composeName(value)} onChange={(event) => update(event.target.value)} /></label>
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
    if (['', 'SOLTERO', 'SOLTERA'].includes(value)) {
      onConyuge({ ...emptyName }, '')
    }
  }

  return (
    <>
      <label>Estado civil
        <select value={estadoCivil} onChange={(event) => updateCivilStatus(event.target.value)}>
          <option value="">Selecciona</option>
          <option value="SOLTERO">SOLTERO</option>
          <option value="SOLTERA">SOLTERA</option>
          <option value="CASADO">CASADO</option>
          <option value="CASADA">CASADA</option>
          <option value="UNION LIBRE">UNIÓN LIBRE</option>
        </select>
      </label>
      <div className={`spouse-name-wrapper ${!spouseEnabled ? 'disabled-name-block' : ''}`}>
        <NameFields
          label="Nombre del cónyuge"
          value={spouseEnabled ? conyugePartes : mergeName(undefined, conyuge)}
          fullName={conyuge}
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
  const title = message.title ?? (
    message.kind === 'loading'
      ? 'Procesando'
      : message.kind === 'success'
        ? 'Listo'
        : message.kind === 'error'
          ? 'No se pudo completar'
          : 'Aviso')

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
  const view: View = pathname === '/formulario' || pathname === '/solicitante' ? 'solicitante' : 'revision'
  const revisionSolicitudId = view === 'revision' ? getRevisionSolicitudId(pathname) : null
  const [requestForm, setRequestForm] = useState<CaptureForm>(mergeForm())
  const [operatorForm, setOperatorForm] = useState<CaptureForm>(mergeForm())
  const [operatorNotes, setOperatorNotes] = useState('')
  const [token, setToken] = useState(() => localStorage.getItem('revisionToken') ?? '')
  const [username, setUsername] = useState(() => localStorage.getItem('revisionUser') ?? '')
  const [login, setLogin] = useState({ username: '', password: '' })
  const [solicitudes, setSolicitudes] = useState<SolicitudResumen[]>([])
  const [listPage, setListPage] = useState(1)
  const [listSearch, setListSearch] = useState('')
  const [listQuery, setListQuery] = useState('')
  const [listMeta, setListMeta] = useState({ total: 0, page: 1, pages: 1 })
  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState('')
  const [listRefresh, setListRefresh] = useState(0)
  const forceListRefresh = useRef(false)
  const [selected, setSelected] = useState<Solicitud | null>(null)
  const [selectedTipo, setTipo] = useState<DocType>('acta')
  const tipo = enabledDocTypes.includes(selectedTipo) ? selectedTipo : enabledDocTypes[0]
  const [pagina, setPagina] = useState(1)
  const [file, setFile] = useState<File | null>(null)
  const [lastExtraction, setLastExtraction] = useState<any>(null)
  const [flash, setFlash] = useState<FlashMessage>(null)
  const [busyAction, setBusyAction] = useState('')
  const [lockLost, setLockLost] = useState(false)
  const [reviewToken, setReviewToken] = useState('')
  const [revisionLease] = useState(revisionBrowserSession)

  function reviewHeaders() {
    return { ...authHeaders(token), 'X-Revision-Lease': revisionLease, 'X-Revision-Token': reviewToken }
  }

  const warnings = useMemo(() => {
    const value = lastExtraction?.resultado?.advertencias
    return Array.isArray(value) ? value : []
  }, [lastExtraction])

  function clearRevisionSession(message = 'Tu sesion expiro. Inicia sesion nuevamente.') {
    localStorage.removeItem('revisionToken')
    localStorage.removeItem('revisionUser')
    setToken('')
    setReviewToken('')
    setUsername('')
    setSolicitudes([])
    setListMeta({ total: 0, page: 1, pages: 1 })
    setListPage(1)
    setListSearch('')
    setListQuery('')
    setSelected(null)
    setOperatorForm(mergeForm())
    setOperatorNotes('')
    setLastExtraction(null)
    setFile(null)
    showMessage('error', message)
    if (window.location.pathname.startsWith('/revision/')) {
      window.history.replaceState({}, '', '/revision')
      setPathname('/revision')
    }
  }

  function handleUnauthorized(response: Response, detail?: string) {
    if (response.status !== 401) return false
    clearRevisionSession(detail || 'Tu sesion expiro. Inicia sesion nuevamente.')
    return true
  }

  useEffect(() => {
    function handlePopState() {
      setPathname(window.location.pathname.replace(/\/$/, '') || '/')
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setListQuery(listSearch.trim())
      setListPage(1)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [listSearch])

  useEffect(() => {
    if (view !== 'revision' || !token || revisionSolicitudId) return
    const controller = new AbortController()
    let active = true
    const force = forceListRefresh.current
    forceListRefresh.current = false
    async function loadInitialSolicitudes() {
      setListLoading(true)
      setListError('')
      const timeout = window.setTimeout(() => controller.abort(), 45_000)
      try {
        const params = new URLSearchParams({ page: String(listPage), page_size: '50', query: listQuery, refresh: String(force) })
        const response = await fetch(`/api/solicitudes/google-sheet?${params}`, { headers: authHeaders(token), signal: controller.signal })
        const payload = await readApiResponse(response)
        if (!active) return
        if (!response.ok) {
          if (handleUnauthorized(response, payload.detail)) return
          throw new Error(payload.detail ?? 'No se pudieron cargar solicitudes.')
        }
        setSolicitudes(payload.items)
        setListMeta({ total: payload.total, page: payload.page, pages: payload.pages })
      } catch (error) {
        if (active) setListError(controller.signal.aborted ? 'La consulta tardo demasiado. Vuelve a actualizar.' : error instanceof Error ? error.message : 'No se pudieron cargar solicitudes.')
      } finally {
        window.clearTimeout(timeout)
        if (active) setListLoading(false)
      }
    }

    loadInitialSolicitudes()
    return () => {
      active = false
      controller.abort()
    }
  }, [view, token, revisionSolicitudId, listPage, listQuery, listRefresh])

  useEffect(() => {
    if (view !== 'revision' || !token || !revisionSolicitudId) return
    const controller = new AbortController()
    async function loadDetail() {
      const response = await fetch(`/api/solicitudes/${revisionSolicitudId}`, { headers: { ...authHeaders(token), 'X-Revision-Lease': revisionLease }, signal: controller.signal })
      const payload = await readApiResponse(response)
      if (controller.signal.aborted) return
      if (!response.ok) {
        if (handleUnauthorized(response, payload.detail)) return
        setSelected(null)
        if (response.status === 409) {
          backToSolicitudes()
          showMessage('info', payload.detail, undefined, response.headers.get('X-Revision-Conflict') === 'active' ? 'Ya tienes una revision activa' : 'Solicitud ocupada')
          return
        }
        throw new Error(payload.detail ?? 'No se encontro la solicitud solicitada.')
      }
      selectSolicitud(payload)
      setLockLost(false)
    }
    loadDetail().catch((error) => {
      if (!controller.signal.aborted) showMessage('error', error instanceof Error ? error.message : 'No se pudo cargar la solicitud.')
    })
    return () => controller.abort()
  }, [view, token, revisionSolicitudId, revisionLease])

  useEffect(() => {
    if (view !== 'revision' || !token || !revisionSolicitudId || !reviewToken) return
    const headers = { ...authHeaders(token), 'X-Revision-Token': reviewToken }
    const url = `/api/solicitudes/${revisionSolicitudId}/bloqueo`
    let active = true
    let renewing = false
    async function renew() {
      if (renewing) return
      renewing = true
      try {
        const response = await fetch(url, { method: 'POST', headers, signal: AbortSignal.timeout(10_000) })
        const payload = await readApiResponse(response)
        if (!active) return
        if (!response.ok) {
          if (handleUnauthorized(response, payload.detail)) return
          setLockLost(true)
          window.clearInterval(timer)
          showMessage('info', payload.detail ?? 'No se pudo renovar el bloqueo.', undefined, 'Revision bloqueada')
        } else {
          setLockLost(false)
        }
      } catch {
        if (active) {
          setLockLost(true)
          window.clearInterval(timer)
          showMessage('info', 'No se pudo confirmar tu bloqueo por un problema de conexion. Tus cambios permanecen en pantalla.', undefined, 'Conexion interrumpida')
        }
      } finally {
        renewing = false
      }
    }
    function release() {
      void fetch(url, { method: 'DELETE', headers, keepalive: true }).catch(() => {})
    }
    function restorePage(event: PageTransitionEvent) {
      if (!event.persisted) return
      setLockLost(true)
      window.clearInterval(timer)
      showMessage('info', 'Esta pagina se restauro despues de salir. Vuelve al panel y abre la solicitud para renovar la reserva.', undefined, 'Reserva no activa')
    }
    const timer = window.setInterval(renew, 120_000)
    window.addEventListener('pagehide', release)
    window.addEventListener('pageshow', restorePage)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('pagehide', release)
      window.removeEventListener('pageshow', restorePage)
      release()
    }
  }, [view, token, revisionSolicitudId, reviewToken])

  const visibleRows = solicitudes.map((item) => item.sheet_row_number).filter((row): row is number => !!row).join(',')
  useEffect(() => {
    if (view !== 'revision' || !token || revisionSolicitudId || !visibleRows) return
    const params = new URLSearchParams()
    visibleRows.split(',').forEach((row) => params.append('rows', row))
    let active = true
    const controller = new AbortController()
    async function poll() {
      try {
        const response = await fetch(`/api/solicitudes/google-sheet/bloqueos?${params}`, { headers: authHeaders(token), signal: controller.signal })
        if (!response.ok) return
        const locks = await response.json()
        if (active) setSolicitudes((items) => items.map((item) => ({ ...item, bloqueo: locks[String(item.sheet_row_number)] ?? null })))
      } catch { /* La siguiente consulta reintenta sin vaciar la tabla. */ }
    }
    const timer = window.setInterval(poll, 10_000)
    return () => { active = false; controller.abort(); window.clearInterval(timer) }
  }, [view, token, revisionSolicitudId, visibleRows])

  function showMessage(kind: FlashKind, text: string, warnings?: string[], title?: string) {
    setFlash({ kind, text, warnings, title })
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

  function loadSolicitudes() {
    forceListRefresh.current = true
    setListRefresh((value) => value + 1)
  }

  function selectSolicitud(solicitud: Solicitud) {
    setReviewToken(solicitud.revision_token ?? '')
    setSelected(solicitud)
    setOperatorForm(mergeForm(solicitud.datos))
    setOperatorNotes(solicitud.notas_operador ?? '')
    setLastExtraction(null)
    setFile(null)
  }

  async function importSheetSolicitud(solicitud: SolicitudResumen) {
    if (!solicitud.sheet_row_number) throw new Error('La fila de Google Sheets no tiene numero de fila.')
    const response = await fetch(`/api/solicitudes/google-sheet/${solicitud.sheet_row_number}/importar`, {
      method: 'POST',
      headers: reviewHeaders(),
    })
    const payload = await readApiResponse(response)
    if (!response.ok) {
      if (handleUnauthorized(response, payload.detail)) return null
      if (response.status === 409) {
        showMessage('info', payload.detail, undefined, response.headers.get('X-Revision-Conflict') === 'active' ? 'Ya tienes una revision activa' : 'Solicitud ocupada')
        return null
      }
      throw new Error(payload.detail ?? 'No se pudo importar la fila de Google Sheets.')
    }
    return payload as Solicitud
  }

  async function navigateToRevision(solicitud: SolicitudResumen) {
    if (solicitud.bloqueo && !solicitud.bloqueo.propio) {
      showMessage('info', `Esta solicitud esta siendo revisada por ${solicitud.bloqueo.nombre}. Podras entrar cuando termine o se libere su bloqueo.`, undefined, 'Solicitud ocupada')
      return
    }
    setBusyAction(`review-${solicitud.id}`)
    try {
      const reviewSolicitud = solicitud.source === 'google_sheet' ? await importSheetSolicitud(solicitud) : null
      if (!reviewSolicitud) return
      selectSolicitud(reviewSolicitud)
      const nextPath = `/revision/${reviewSolicitud.id}`
      window.history.pushState({}, '', nextPath)
      setPathname(nextPath)
    } catch (error) {
      showMessage('error', error instanceof Error ? error.message : 'No se pudo abrir la solicitud.')
    } finally {
      setBusyAction('')
    }
  }

  function backToSolicitudes() {
    window.history.pushState({}, '', '/revision')
    setPathname('/revision')
    setSelected(null)
    setLastExtraction(null)
    setFile(null)
    setReviewToken('')
  }

  async function releaseSolicitud() {
    if (!selected) return
    setBusyAction('release')
    try {
      const response = await fetch(`/api/solicitudes/${selected.id}/bloqueo`, { method: 'DELETE', headers: reviewHeaders() })
      if (!response.ok) {
        const payload = await readApiResponse(response)
        if (handleUnauthorized(response, payload.detail)) return
        throw new Error(payload.detail ?? 'No se pudo liberar la solicitud.')
      }
      backToSolicitudes()
      showMessage('success', 'La solicitud quedo disponible para otro revisor. Los cambios sin guardar no se conservaron.', undefined, 'Solicitud liberada')
    } catch (error) {
      showMessage('error', error instanceof Error ? error.message : 'No se pudo liberar la solicitud.')
    } finally {
      setBusyAction('')
    }
  }

  async function logoutOperator() {
    try {
      const response = await fetch('/api/auth/logout', { method: 'POST', headers: authHeaders(token) })
      if (!response.ok) {
        const payload = await readApiResponse(response)
        if (handleUnauthorized(response, payload.detail)) return
        throw new Error(payload.detail ?? 'No se pudo cerrar la sesion.')
      }
      clearRevisionSession('Sesion cerrada.')
      showMessage('success', 'Se cerro la sesion y se liberaron tus solicitudes.', undefined, 'Sesion cerrada')
    } catch (error) {
      showMessage('error', error instanceof Error ? error.message : 'No se pudo cerrar la sesion.')
    }
  }

  async function handleExtraction(event: FormEvent) {
    event.preventDefault()
    if (!file) {
      showMessage('error', 'Selecciona una imagen o PDF.')
      return
    }

    setBusyAction('extract')
    showMessage('loading', tipo === 'qr_acta' ? 'Leyendo QR y consultando enlace...' : 'Analizando documento...')

    let response: Response
    let payload: any
    try {
      const uploadFile = await prepareImageForOcr(file)
      const body = new FormData()
      body.append('tipo', tipo)
      body.append('pagina', String(pagina))
      body.append('archivo', uploadFile)

      const controller = new AbortController()
      const timeoutId = window.setTimeout(() => controller.abort(), tipo === 'acta' ? 60_000 : 35_000)
      response = await fetch('/api/extracciones', {
        method: 'POST',
        headers: authHeaders(token),
        body,
        signal: controller.signal,
      })
      window.clearTimeout(timeoutId)
      payload = await readApiResponse(response)
    } catch (error) {
      setBusyAction('')
      if (error instanceof DOMException && error.name === 'AbortError') {
        showMessage('error', 'El analisis tardo demasiado. Intenta con una imagen recortada, derecha y con buena iluminacion.')
        return
      }
      showMessage('error', error instanceof Error ? error.message : 'No se pudo preparar el documento.')
      return
    }
    setBusyAction('')
    if (!response.ok) {
      if (handleUnauthorized(response, payload.detail)) return
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
    if (!selected || lockLost) return
    setBusyAction('save')
    showMessage('loading', 'Guardando revisión...')
    try {
      const cleanForm = normalizeDeep(operatorForm)
      const extracciones = lastExtraction ? [...(selected.extracciones ?? []), lastExtraction] : selected.extracciones ?? []
      const response = await fetch(`/api/solicitudes/${selected.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...reviewHeaders() },
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
      if (!response.ok) {
        if (handleUnauthorized(response, payload.detail)) return
        if (response.status === 409) {
          setLockLost(true)
          showMessage('info', payload.detail, undefined, 'No se puede guardar')
          return
        }
        if (response.headers.get('X-Revision-Released') === 'true') backToSolicitudes()
        showMessage('error', payload.detail ?? 'No se pudo guardar la revisión.')
        return
      }
      backToSolicitudes()
      showMessage('success', `Revision guardada por ${payload.revisado_por}. La solicitud quedo liberada.`, undefined, 'Revision guardada')
    } catch (error) {
      showMessage('error', error instanceof Error ? error.message : 'No se pudo confirmar el guardado. Vuelve a intentarlo.')
    } finally {
      setBusyAction('')
    }
  }

  async function downloadExcel() {
    if (!selected || lockLost) return
    setBusyAction('excel')
    showMessage('loading', 'Generando Excel...')
    const cleanForm = normalizeDeep(operatorForm)
    const response = await fetch(`/api/solicitudes/${selected.id}/excel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...reviewHeaders() },
      body: JSON.stringify({
        datos: cleanForm,
      }),
    })
    if (!response.ok) {
      const payload = await readApiResponse(response)
      setBusyAction('')
      if (handleUnauthorized(response, payload.detail)) return
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
          <a className="brand" href="/revision" aria-label="SEIEM, acceso de revision">
            <span className="brand-wordmark">SEIEM<span aria-hidden="true">.</span></span>
            <span className="brand-description">Servicios Educativos Integrados<br />al Estado de México</span>
          </a>
          <div className="topbar-context">
            <span className="platform-label">Plataforma de filiación</span>
            {view === 'revision' && token
              ? <><span className="operator-badge"><Lock size={14} aria-hidden="true" /> {username}</span><button className="secondary icon-button" type="button" onClick={logoutOperator} aria-label="Cerrar sesion" title="Cerrar sesion"><LogOut size={17} /></button></>
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
                  <span>{listMeta.total} registro{listMeta.total === 1 ? '' : 's'}{listQuery ? ' encontrados' : ' disponibles'}</span>
                </div>
                <button className="secondary" type="button" onClick={loadSolicitudes} disabled={listLoading}>
                  <RefreshCw size={17} /> {listLoading ? 'Cargando...' : 'Actualizar'}
                </button>
              </div>
              <label className="requests-search"><Search size={18} aria-hidden="true" /><input type="search" aria-label="Buscar solicitudes" placeholder="Nombre, correo, CURP, telefono o fila" maxLength={200} value={listSearch} onChange={(event) => setListSearch(event.target.value)} /></label>
              {listError && <p role="alert">{listError}</p>}
              <div className="requests-table-wrapper" aria-busy={listLoading}>
                <table className="requests-table">
                  <thead>
                    <tr>
                      <th>Solicitante</th>
                      <th>CURP</th>
                      <th>Contacto</th>
                      <th>Fecha</th>
                      <th>En revisión por</th>
                      <th>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {solicitudes.map((solicitud) => (
                      <tr className={selected?.id === solicitud.id ? 'selected' : ''} key={solicitud.id}>
                        <td data-label="Solicitante">
                          <strong>{solicitudName(solicitud)}</strong>
                          <span>{solicitud.source === 'google_sheet' ? `Fila ${solicitud.sheet_row_number}` : `ID ${solicitud.id}`}</span>
                        </td>
                        <td data-label="CURP">{solicitud.curp || solicitud.datos?.curp || 'Pendiente'}</td>
                        <td data-label="Contacto">{solicitudEmail(solicitud)}</td>
                        <td data-label="Fecha">{new Date(solicitud.created_at).toLocaleString()}</td>
                        <td data-label="En revisión por">{solicitud.bloqueo ? <span className="review-lock-owner"><Lock size={13} />{solicitud.bloqueo.nombre}</span> : 'Disponible'}</td>
                        <td data-label="Acción">
                          <button className="review-button" type="button" disabled={busyAction === `review-${solicitud.id}`} onClick={() => navigateToRevision(solicitud)}>
                            {solicitud.bloqueo && !solicitud.bloqueo.propio ? <Lock size={16} /> : <FileSearch size={16} />} {busyAction === `review-${solicitud.id}` ? 'Abriendo...' : solicitud.bloqueo && !solicitud.bloqueo.propio ? 'Ocupada' : 'Revisar'}
                          </button>
                        </td>
                      </tr>
                    ))}
                    {solicitudes.length === 0 && (
                      <tr>
                        <td className="empty-table" colSpan={6}><ListChecks size={28} aria-hidden="true" /><strong>{listLoading ? 'Cargando solicitudes...' : listError ? 'No se pudo cargar la tabla' : listQuery ? 'Sin coincidencias' : 'Aún no hay solicitudes'}</strong></td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <nav className="requests-pagination" aria-label="Paginas de solicitudes">
                <span aria-live="polite">{listMeta.total ? `${(listMeta.page - 1) * 50 + 1}-${Math.min(listMeta.page * 50, listMeta.total)} de ${listMeta.total}` : '0 registros'}</span>
                <div>
                  <button className="secondary" type="button" aria-label="Pagina anterior" title="Pagina anterior" disabled={listLoading || listMeta.page <= 1} onClick={() => setListPage(listMeta.page - 1)}><ChevronLeft size={18} /></button>
                  <span>Pagina {listMeta.page} de {listMeta.pages}</span>
                  <button className="secondary" type="button" aria-label="Pagina siguiente" title="Pagina siguiente" disabled={listLoading || listMeta.page >= listMeta.pages} onClick={() => setListPage(listMeta.page + 1)}><ChevronRight size={18} /></button>
                </div>
              </nav>
            </div>
            )}

            {revisionSolicitudId && (
            <div className="form-layout">
            {selected && <SectionNav items={reviewSections} review />}
            <div className="review-panel">
              {selected ? (
                <>
                  <div className="review-toolbar">
                    <button className="secondary" type="button" onClick={releaseSolicitud} disabled={busyAction === 'release'}><Unlock size={18} /> Liberar solicitud</button>
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
                      <span>Fecha</span>
                      <strong>{new Date(selected.created_at).toLocaleString()}</strong>
                    </div>
                  </section>

                  <section className="document-panel" id="documentos" aria-label="Documentos">
                    <form className="upload-panel" onSubmit={handleExtraction}>
                      <SectionHeading number="01" title="Análisis de acta de nacimiento" />
                      {enabledDocTypes.length > 1 && <div className="segmented" role="group" aria-label="Tipo de documento">
                        {enabledDocTypes.includes('ine') && <button type="button" aria-pressed={tipo === 'ine'} className={tipo === 'ine' ? 'selected' : ''} onClick={() => setTipo('ine')}>INE</button>}
                        <button type="button" aria-pressed={tipo === 'acta'} className={tipo === 'acta' ? 'selected' : ''} onClick={() => setTipo('acta')}>Acta</button>
                        {enabledDocTypes.includes('qr_acta') && <button type="button" aria-pressed={tipo === 'qr_acta'} className={tipo === 'qr_acta' ? 'selected' : ''} onClick={() => setTipo('qr_acta')}><QrCode size={16} /> QR acta</button>}
                      </div>}
                      <label className="file-drop">
                        <Upload size={22} />
                        <span>{file ? file.name : 'Seleccionar acta (imagen o PDF)'}</span>
                        <input type="file" accept=".jpg,.jpeg,.png,.bmp,.tif,.tiff,.webp,.pdf" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} />
                      </label>
                      {tipo === 'ine' && <label className="inline-label">Página PDF<input type="number" min="1" value={pagina} onChange={(event) => setPagina(Number(event.target.value))} /></label>}
                      <button className="secondary" type="submit" disabled={!file || busyAction === 'extract'}>
                        {tipo === 'qr_acta' ? <QrCode size={18} /> : <FileSearch size={18} />}{documentActionLabel(tipo, busyAction === 'extract')}
                      </button>
                      {warnings.length > 0 && <ul className="warnings">{warnings.map((warning: string, index: number) => <li key={index}>{warning}</li>)}</ul>}
                    </form>
                  </section>

                  {lockLost && <p role="alert" className="notice">Revision bloqueada. Tus cambios siguen en pantalla; vuelve a abrir la solicitud para continuar.</p>}
                  <fieldset className="review-lock-fieldset" disabled={lockLost}>
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
                  </fieldset>
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
          fullName={form.nombreCompleto}
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
                fullName={reference.nombre}
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
          fullName={form.nombreCompleto}
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
            fullName={form.padre}
            onChange={(parts, fullName) => {
              setField('padreNombrePartes', parts)
              setField('padre', fullName)
            }}
          />
          <NameFields
            label="Nombre de la madre"
            value={form.madreNombrePartes}
            fullName={form.madre}
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
                fullName={reference.nombre}
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

