import { forwardRef } from 'react'

// Zone de saisie arrondie : « + » (ajout de PDF) à gauche, envoi à droite.
const Composer = forwardRef(function Composer(
  { value, onChange, onSubmit, onAttach, disabled, banner },
  ref,
) {
  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit()
    }
  }

  return (
    <div className="rounded-2xl border border-gray-700 bg-gray-900 shadow-lg shadow-black/30 focus-within:border-gray-600 transition-colors">
      {banner}
      <div className="flex items-end gap-2 px-3 py-2.5">
        <button
          type="button"
          onClick={onAttach}
          disabled={disabled}
          title="Ajouter des PDF à l'index"
          className="shrink-0 w-8 h-8 rounded-lg text-gray-400 hover:text-gray-100 hover:bg-gray-800 disabled:opacity-40 flex items-center justify-center text-xl leading-none transition-colors"
        >
          +
        </button>
        <textarea
          ref={ref}
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          rows={1}
          placeholder="Posez une question sur vos documents…"
          className="flex-1 resize-none bg-transparent py-1.5 text-[15px] text-gray-100 placeholder-gray-500 focus:outline-none disabled:opacity-50 max-h-44 overflow-y-auto"
          style={{ fieldSizing: 'content' }}
        />
        <button
          type="button"
          onClick={onSubmit}
          disabled={disabled || !value.trim()}
          title="Envoyer"
          className="shrink-0 w-8 h-8 rounded-full bg-gray-100 text-gray-900 hover:bg-white disabled:bg-gray-700 disabled:text-gray-500 flex items-center justify-center transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" />
          </svg>
        </button>
      </div>
    </div>
  )
})

export default Composer
