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

const NotAuthorized = ({ mode }) => {
  // Vars
  const darkImg = '/images/pages/misc-mask-4-dark.png'
  const lightImg = '/images/pages/misc-mask-4-light.png'

  // Hooks
  const { lang: locale } = useParams()
  const miscBackground = useImageVariant(mode, lightImg, darkImg)

  return (
    <div className='flex items-center justify-center min-bs-[100dvh] relative p-6 overflow-x-hidden'>
      <div className='flex items-center flex-col text-center gap-10'>
        <div className='flex flex-col gap-2 is-[90vw] sm:is-[unset]'>
          <Typography className='text-8xl font-medium' color='text.primary'>
            401
          </Typography>
          <Typography variant='h4'>You are not authorized! 🔐</Typography>
          <Typography>You don&#39;t have permission to access this page. Go Home!</Typography>
        </div>
        <img
          alt='error-illustration'
          src='/images/illustrations/characters/6.png'
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

export default NotAuthorized
