import { Component, type ErrorInfo, type ReactNode } from 'react'

/** Keeps one broken view from blanking the whole app. */
export default class ErrorBoundary extends Component<
  { children: ReactNode; resetKey?: string },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack)
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="rounded-xl border border-critical/40 bg-card p-5">
        <p className="font-medium text-critical">Something went wrong on this page.</p>
        <p className="mt-1 text-sm text-ink-2">{this.state.error.message}</p>
        <button
          onClick={() => this.setState({ error: null })}
          className="mt-3 rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-hover"
        >
          Try again
        </button>
      </div>
    )
  }
}
