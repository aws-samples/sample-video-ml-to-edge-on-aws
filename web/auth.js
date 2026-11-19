// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
//
// Cognito sign-in with USER_PASSWORD_AUTH over plain fetch, so the page loads no
// third-party code. The ID token lives in sessionStorage: it survives a reload of
// this tab and is gone when the tab closes.
'use strict';

const Auth = (() => {
  const KEY = 'conveyor.idToken';
  let config;
  let pending;

  async function call(target, body) {
    const response = await fetch(`https://cognito-idp.${config.region}.amazonaws.com/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-amz-json-1.1', 'X-Amz-Target': `AWSCognitoIdentityProviderService.${target}` },
      body: JSON.stringify(body),
    });
    const doc = await response.json();
    if (!response.ok) throw new Error(doc.message || doc.__type);
    return doc;
  }

  function claims(token) {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(payload));
  }

  function session() {
    const token = sessionStorage.getItem(KEY);
    if (!token) return null;
    const c = claims(token);
    if (c.exp * 1000 < Date.now()) {
      sessionStorage.removeItem(KEY);
      return null;
    }
    return { token, username: c['cognito:username'], sub: c.sub, site: (c['cognito:groups'] || [])[0] || '' };
  }

  function finish(result) {
    sessionStorage.setItem(KEY, result.AuthenticationResult.IdToken);
    pending = null;
    return { done: true, session: session() };
  }

  // Resolves to {done, session} once signed in, or {done: false} when Cognito
  // asks for a new password first (an administrator-created account).
  async function signIn(username, password) {
    const result = await call('InitiateAuth', {
      ClientId: config.userPoolClientId, AuthFlow: 'USER_PASSWORD_AUTH',
      AuthParameters: { USERNAME: username, PASSWORD: password },
    });
    if (result.ChallengeName === 'NEW_PASSWORD_REQUIRED') {
      pending = { username, session: result.Session };
      return { done: false };
    }
    return finish(result);
  }

  async function setNewPassword(newPassword) {
    const result = await call('RespondToAuthChallenge', {
      ClientId: config.userPoolClientId, ChallengeName: 'NEW_PASSWORD_REQUIRED', Session: pending.session,
      ChallengeResponses: { USERNAME: pending.username, NEW_PASSWORD: newPassword },
    });
    return finish(result);
  }

  function signOut() {
    sessionStorage.removeItem(KEY);
  }

  return {
    init(c) { config = c; },
    session, signIn, setNewPassword, signOut,
    needsNewPassword: () => Boolean(pending),
  };
})();
