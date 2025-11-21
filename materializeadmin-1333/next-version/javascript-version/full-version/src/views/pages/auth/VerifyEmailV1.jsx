'use client'

// Next Imports
import { useParams } from 'next/navigation'

// MUI Imports
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Typography from '@mui/material/Typography'
import Button from '@mui/material/Button'

// Component Imports
import Link from '@components/Link'
import Logo from '@components/layout/shared/Logo'

// Hook Imports
import { useImageVariant } from '@core/hooks/useImageVariant'

// Util Imports
import { getLocalizedUrl } from '@/utils/i18n'

const VerifyEmailV1 = ({ mode }) => {
  // Vars
  const darkImg = '/images/pages/auth-v1-mask-1-dark.png'
  const lightImg = '/images/pages/auth-v1-mask-1-light.png'

  // Hooks
  const { lang: locale } = useParams()
  const authBackground = useImageVariant(mode, lightImg, darkImg)

  return (
    <div className='flex flex-col justify-center items-center min-bs-[100dvh] is-full relative p-6'>
      <Card className='flex flex-col sm:is-[460px]'>
        <CardContent className='p-6 sm:!p-12'>
          <Link href={getLocalizedUrl('/', locale)} className='flex justify-center items-center mbe-6'>
            <Logo />
          </Link>
          <Typography variant='h4'>Verify your email ✉️</Typography>
          <div className='flex flex-col gap-5'>
            <Typography className='mbs-1'>
              Account activation link sent to your email address:{' '}
              <span className='font-medium text-textPrimary'>john.doe@email.com</span> Please follow the link inside to
              continue.
            </Typography>
            <Button fullWidth variant='contained' type='submit'>
              Skip For Now
            </Button>
            <div className='flex justify-center items-center flex-wrap gap-2'>
              <Typography>Didn&#39;t get the mail?</Typography>
              <Typography color='primary' component={Link}>
                Resend
              </Typography>
            </div>
          </div>
        </CardContent>
      </Card>
      <img src={authBackground} className='absolute bottom-[5%] z-[-1] is-full max-md:hidden' />
    </div>
  )
}

export default VerifyEmailV1
