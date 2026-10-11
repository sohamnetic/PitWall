import type { SVGProps } from 'react'

// 24px stroke icons (1.75 stroke, round caps), inherit the text color.
function Icon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...props}
    />
  )
}

export const FlagIcon = () => (
  <Icon>
    <path d="M5 21V4" />
    <path d="M5 4h10l-1.5 3.5L15 11H5" />
  </Icon>
)

export const AskIcon = () => (
  <Icon>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />
    <path d="M10 9.5a2.3 2.3 0 1 1 3.2 2.1c-.7.3-1.2.9-1.2 1.6" />
    <path d="M12 16.2h.01" />
  </Icon>
)

export const TrophyIcon = () => (
  <Icon>
    <path d="M8 4h8v5a4 4 0 0 1-8 0V4Z" />
    <path d="M8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4" />
    <path d="M12 13v4M8.5 20h7M10 17h4" />
  </Icon>
)

export const ListIcon = () => (
  <Icon>
    <path d="M9 6h11M9 12h11M9 18h11" />
    <path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01" />
  </Icon>
)

export const ChartIcon = () => (
  <Icon>
    <path d="M4 20V10M10 20V4M16 20v-7M21 20H3" />
  </Icon>
)

export const PeopleIcon = () => (
  <Icon>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
    <path d="M16 5.2a3 3 0 0 1 0 5.6M18 19a5 5 0 0 0-2.5-4.3" />
  </Icon>
)

export const ArrowUp = () => (
  <Icon width="16" height="16">
    <path d="M12 19V5M6 11l6-6 6 6" />
  </Icon>
)

export const ArrowDown = () => (
  <Icon width="16" height="16">
    <path d="M12 5v14M6 13l6 6 6-6" />
  </Icon>
)
