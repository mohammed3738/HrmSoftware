'use client'

// Next Imports
import Link from 'next/link'
import { useParams } from 'next/navigation'

// MUI Imports
import Button from '@mui/material/Button'
import Typography from '@mui/material/Typography'

// Hook Imports
import { useImageVariant } from '@core/hooks/useImageVariant'

// Util Imports
import { getLocalizedUrl } from '@/utils/i18n'

const UnderMaintenance = ({ mode }) => {
  // Vars
  const darkImg = '/images/pages/misc-mask-2-dark.png'
  const lightImg = '/images/pages/misc-mask-2-light.png'

  // Hooks
  const { lang: locale } = useParams()
  const miscBackground = useImageVariant(mode, lightImg, darkImg)

  return (
    <div className='flex items-center justify-center min-bs-[100dvh] relative p-6 overflow-x-hidden'>
      <div className='flex items-center flex-col text-center gap-10'>
        <div className='flex flex-col gap-2 is-[90vw] sm:is-[unset]'>
          <Typography variant='h4'>Under Maintenance! 🚧</Typography>
          <Typography>Sorry for the inconvenience but we&#39;re performing some maintenance at the moment</Typography>
        </div>
        <img
          alt='error-illustration'
          src='/images/illustrations/characters/4.png'
          className='object-cover bs-[400px] md:bs-[450px] lg:bs-[500px]'
        />
        <Button href={getLocalizedUrl('/', locale)} component={Link} variant='contained'>
          Back to Home
        </Button>
      </div>
      <img src={miscBackground} className='absolute bottom-0 z-[-1] is-full max-md:hidden' />
    </div>
  )
}

export default UnderMaintenance
