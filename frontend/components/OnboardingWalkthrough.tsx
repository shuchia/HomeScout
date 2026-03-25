'use client'
import { useState, useEffect } from 'react'
import { ACTIONS, EVENTS, Joyride, STATUS } from 'react-joyride'
import type { EventData, Controls, Step } from 'react-joyride'
import { useAuth } from '@/contexts/AuthContext'
import { supabase } from '@/lib/supabase'

const STEP_OPTIONS: Partial<import('react-joyride').Options> = {
  showProgress: true,
  overlayClickAction: false,
  primaryColor: '#2D6A4F',
  buttons: ['back', 'close', 'primary', 'skip'],
}

const STEPS: Step[] = [
  {
    target: 'body',
    placement: 'center',
    skipBeacon: true,
    title: 'Welcome to snugd!',
    content: 'Find apartments across 19 East Coast cities. Set your budget and preferences, and we\'ll match you with the best options.',
    ...STEP_OPTIONS,
  },
  {
    target: '[data-onboarding="favorites"]',
    title: 'Save Your Favorites',
    content: 'Tap the heart icon to save apartments you love. Compare them side by side to find your perfect match.',
    placement: 'bottom',
    skipBeacon: true,
    ...STEP_OPTIONS,
  },
  {
    target: '[data-onboarding="tours"]',
    title: 'Plan Your Tours',
    content: 'Plan tours, capture notes and photos, and get AI-powered insights to help you decide.',
    placement: 'bottom',
    skipBeacon: true,
    ...STEP_OPTIONS,
  },
  {
    target: 'body',
    placement: 'center',
    skipBeacon: true,
    title: 'Unlock Pro Features',
    content: 'Get AI scoring, smart comparisons, and inquiry emails with a Pro invite code. Enter it on the search page or the Pricing page.',
    ...STEP_OPTIONS,
  },
]

export function OnboardingWalkthrough() {
  const { user, profile, refreshProfile } = useAuth()
  const [run, setRun] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)

  useEffect(() => {
    if (user && profile && !profile.has_completed_onboarding) {
      const timer = setTimeout(() => setRun(true), 1000)
      return () => clearTimeout(timer)
    }
  }, [user, profile])

  async function markComplete() {
    if (!user) return
    try {
      await supabase
        .from('profiles')
        .update({ has_completed_onboarding: true })
        .eq('id', user.id)
      await refreshProfile()
    } catch {
      // Non-critical
    }
  }

  function handleEvent(data: EventData, controls: Controls) {
    const { status, action, type } = data

    if (status === STATUS.FINISHED || status === STATUS.SKIPPED) {
      setRun(false)
      markComplete()
      return
    }

    if (type === EVENTS.STEP_AFTER) {
      if (action === ACTIONS.NEXT) {
        setStepIndex(prev => prev + 1)
      } else if (action === ACTIONS.PREV) {
        setStepIndex(prev => prev - 1)
      } else if (action === ACTIONS.CLOSE) {
        controls.next()
      }
    }
  }

  if (!user || !profile || profile.has_completed_onboarding) return null

  return (
    <Joyride
      steps={STEPS}
      run={run}
      stepIndex={stepIndex}
      onEvent={handleEvent}
      continuous
      styles={{
        tooltip: {
          borderRadius: '12px',
          fontSize: '14px',
        },
        buttonPrimary: {
          borderRadius: '8px',
          padding: '8px 16px',
        },
        buttonBack: {
          color: '#6B7280',
        },
      }}
      locale={{
        last: 'Get Started',
        skip: 'Skip Tour',
      }}
    />
  )
}
